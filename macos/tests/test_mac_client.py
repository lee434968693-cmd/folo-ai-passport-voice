"""No real keys, drivers, recordings or device: fake native backends + real UDP."""
import argparse
import asyncio
import json
from pathlib import Path
import socket
import struct
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mac_voice as m
import mac_audio as audio
import mac_keys as keys
import mac_network as network
from udp_transport import UdpTransport, UdpError, EVENT_UUID, AUDIO_UUID


class FakeQuartz:
    kCGEventFlagsChanged = 12
    kCGHIDEventTap = 0

    def __init__(self):
        self.events = []
        self.allowed = True
        self.fail_code = None

    def CGPreflightPostEventAccess(self):
        return self.allowed

    def CGEventCreateKeyboardEvent(self, source, code, down):
        if self.fail_code == code and down:
            raise RuntimeError('simulated event failure')
        return dict(code=code, down=down, type='key')

    def CGEventSetFlags(self, event, flags):
        event['flags'] = flags

    def CGEventSetType(self, event, event_type):
        event['type'] = event_type

    def CGEventPost(self, tap, event):
        self.events.append(event.copy())


def keyboard():
    q = FakeQuartz()
    ax = types.SimpleNamespace(AXIsProcessTrusted=lambda: q.allowed)
    return keys.QuartzKeyboard(q, ax)


def sounddevice(streams=None, devices=None):
    return types.SimpleNamespace(
        query_devices=lambda: devices if devices is not None else [
            dict(name='BlackHole 2ch', max_input_channels=2, max_output_channels=2)],
        CoreAudioSettings=mock.Mock(side_effect=lambda **kw: kw),
        RawOutputStream=mock.Mock(side_effect=streams or [mock.Mock()]))


def args():
    return argparse.Namespace(key='cmd+f9', mode='hold', port=33333,
                              device_ip='', output_substr='BlackHole 2ch')


def event(name, **extra):
    return (json.dumps(dict(event=name, **extra)) + '\n').encode()


class KeysTest(unittest.TestCase):
    def test_apple_codes_and_invalid_combinations(self):
        self.assertEqual(keys.resolve_key_spec('cmd+f9'), [55, 101])
        self.assertEqual(keys.resolve_key_spec('option+return'), [58, 36])
        for bad in ('cmd+cmd', 'f9+cmd', 'unknown', '', 'cmd+'):
            with self.assertRaises(ValueError):
                keys.resolve_key_spec(bad)

    def test_hold_flags_and_reverse_release_are_idempotent(self):
        backend = keyboard()
        injector = keys.MacKeyInjector('cmd+f9', 'hold', backend)
        injector.start()
        injector.start()
        injector.stop()
        injector.stop()
        self.assertEqual([(e['code'], e['down']) for e in backend.q.events],
                         [(55, True), (101, True), (101, False), (55, False)])
        self.assertEqual([e['flags'] for e in backend.q.events], [1 << 20] * 3 + [0])
        self.assertEqual(backend.q.events[0]['type'], 12)
        self.assertFalse(injector._held)

    def test_tap_starts_and_stops_once(self):
        backend = keyboard()
        injector = keys.MacKeyInjector('f9', 'tap', backend)
        with mock.patch.object(keys.time, 'sleep'):
            injector.start()
            injector.stop()
            injector.stop()
        self.assertEqual([e['down'] for e in backend.q.events], [True, False] * 2)

    def test_permission_denial_never_posts_key_down(self):
        backend = keyboard()
        backend.q.allowed = False
        injector = keys.MacKeyInjector('f9', 'hold', backend)
        with self.assertRaises(keys.KeyErrorMac):
            injector.start()
        self.assertFalse(any(e['down'] for e in backend.q.events))
        self.assertFalse(injector._active)

    def test_partial_failure_releases_previously_pressed_modifier(self):
        backend = keyboard()
        backend.q.fail_code = 101
        injector = keys.MacKeyInjector('cmd+f9', 'hold', backend)
        with self.assertRaises(keys.KeyErrorMac):
            injector.start()
        self.assertEqual((backend.q.events[-1]['code'], backend.q.events[-1]['down']), (55, False))
        self.assertFalse(backend.modifiers)
        self.assertFalse(injector._held)
        self.assertFalse(backend.ready)

    def test_permission_revoked_still_attempts_key_up(self):
        backend = keyboard()
        injector = keys.MacKeyInjector('f9', 'hold', backend)
        injector.start()
        backend.q.allowed = False
        injector.stop()
        self.assertFalse(backend.q.events[-1]['down'])


class AudioTest(unittest.TestCase):
    def test_stereo_preserves_signed_pcm_and_both_channels(self):
        samples = [-32768, -1, 0, 1, 32767]
        data = struct.pack('<5h', *samples)
        self.assertEqual(struct.unpack('<10h', audio.stereo_pcm(data)),
                         tuple(x for sample in samples for x in (sample, sample)))
        with self.assertRaises(ValueError):
            audio.stereo_pcm(b'x')

    def test_coreaudio_converts_without_changing_global_sample_rate(self):
        sd = sounddevice()
        sink = audio.make_audio_sink(m.shared, 'BlackHole', sd, start_thread=False)
        self.assertTrue(sink.enabled)
        options = sd.RawOutputStream.call_args.kwargs
        self.assertEqual((options['samplerate'], options['channels']), (16000, 2))
        self.assertFalse(options['extra_settings']['change_device_parameters'])
        self.assertFalse(options['extra_settings']['fail_if_conversion_required'])
        sink.close()
        sink.close()

    def test_failed_first_endpoint_is_closed_before_fallback(self):
        first, second = mock.Mock(), mock.Mock()
        first.start.side_effect = RuntimeError('format unavailable')
        sd = sounddevice([first, second], [dict(name='BlackHole 2ch', max_output_channels=2)] * 2)
        sink = audio.make_audio_sink(m.shared, 'BlackHole', sd, start_thread=False)
        self.assertTrue(sink.enabled)
        first.close.assert_called_once()
        self.assertIs(sink._stream, second)
        sink.close()

    def test_no_route_never_claims_audio_ready(self):
        sd = sounddevice(devices=[dict(name='Built-in Speakers', max_output_channels=2)])
        sink = audio.make_audio_sink(m.shared, 'BlackHole', sd, start_thread=False)
        self.assertFalse(sink.enabled)
        sd.RawOutputStream.assert_not_called()
        sink.close()

    def test_thread_start_failure_closes_stream_and_clears_readiness(self):
        stream = mock.Mock()
        with mock.patch.object(audio.threading, 'Thread') as thread:
            thread.return_value.start.side_effect = RuntimeError('thread failure')
            sink = audio.make_audio_sink(m.shared, 'BlackHole', sounddevice([stream]))
        self.assertFalse(sink.enabled)
        stream.close.assert_called_once()

    def test_decode_is_bounded_to_five_frames(self):
        sink = audio.make_audio_sink(m.shared, 'BlackHole', sounddevice(), start_thread=False)
        for _ in range(20):
            sink.write_block(bytes(804))
        self.assertEqual(sink._q.qsize(), 5)
        self.assertEqual(sink._q.unfinished_tasks, 5)
        self.assertEqual(len(sink._q.queue[0]), 3200)
        sink.close()
        self.assertEqual(sink._q.unfinished_tasks, 0)

    def test_writer_failure_disables_and_accounts_for_every_frame(self):
        stream = mock.Mock()
        stream.write.side_effect = RuntimeError('driver removed')
        sink = audio.make_audio_sink(m.shared, 'BlackHole', sounddevice([stream]), start_thread=False)
        sink.write_block(bytes(804))
        sink.write_block(bytes(804))
        sink._writer()
        self.assertFalse(sink.enabled)
        self.assertEqual(sink._q.unfinished_tasks, 0)
        sink.close()


class NetworkTest(unittest.TestCase):
    def test_actual_netmasks_exclude_loopback_and_tunnels(self):
        fixture = '''lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
    inet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
    inet 192.168.20.3 netmask 0xfffff000 broadcast 192.168.31.255
en1: flags=8863<UP,BROADCAST,RUNNING> mtu 1500
    inet 10.3.4.5 netmask 255.255.255.0 broadcast 10.3.4.255
utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
    inet 10.99.0.1 netmask 0xffffff00
en2: flags=8862<BROADCAST,RUNNING> mtu 1500
    inet 192.168.90.5 netmask 0xffffff00
'''
        self.assertEqual(network.parse_broadcasts(fixture),
                         ['10.3.4.255', '192.168.31.255', '255.255.255.255'])

    def test_failed_ifconfig_falls_back_without_modifying_network(self):
        with mock.patch.object(network.subprocess, 'run', side_effect=OSError):
            self.assertEqual(network.broadcast_targets(12345), [('255.255.255.255', 12345)])

    def test_invalid_mask_is_ignored(self):
        self.assertEqual(network.parse_broadcasts('en0: flags=3<UP,BROADCAST>\n'
            '\tinet 10.0.0.1 netmask 0xff00ff00'), ['255.255.255.255'])


class ForwarderTest(unittest.TestCase):
    def setUp(self):
        self.backend = keyboard()
        self.sink = mock.Mock(enabled=True)
        self.forwarder = m.MacForwarder(args(), self.backend, self.sink)
        # Any accidental Windows key injection is a test failure.
        self.patch = mock.patch.object(m.shared, '_send_key', side_effect=AssertionError('Windows injection'))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_permission_status_and_blocked_start(self):
        self.backend.q.allowed = False
        self.assertFalse(self.forwarder.pc_status()['hotkeyReady'])
        self.forwarder.on_event(event('voice.start'))
        self.assertFalse(self.forwarder.active)
        self.assertFalse(self.backend.q.events)

    def test_end_drains_before_release(self):
        self.forwarder.on_event(event('voice.start'))
        def drain():
            self.assertTrue(self.forwarder.injector._held)
        self.sink.drain.side_effect = drain
        self.forwarder.on_event(event('voice.end'))
        self.sink.drain.assert_called_once()
        self.assertFalse(self.forwarder.injector._held)

    def test_lost_end_releases_even_when_link_is_alive(self):
        self.forwarder.on_event(event('voice.start'))
        self.forwarder.check_health(self.forwarder.last_audio_at + 3)
        self.assertFalse(self.forwarder.active)
        self.assertFalse(self.forwarder.injector._held)

    def test_revoked_permission_releases_before_accepting_more_audio(self):
        self.forwarder.on_event(event('voice.start'))
        self.backend.q.allowed = False
        self.forwarder.on_audio(bytes([0, 128]) + bytes(804))
        self.sink.write_block.assert_not_called()
        self.assertFalse(self.forwarder.active)
        self.assertFalse(self.backend.q.events[-1]['down'])

    def test_disconnect_releases_and_malformed_events_are_ignored(self):
        for payload in (b'null', b'[]', b'bad', b'\xff'):
            self.forwarder.on_event(payload)
        self.forwarder.on_event(event('voice.start'))
        self.forwarder.on_disconnect()
        self.assertFalse(self.forwarder.injector._held)

    def test_mac_transport_uses_mac_network_provider(self):
        transport = self.forwarder.make_transport()
        self.assertIs(transport._broadcast_targets, m.broadcast_targets)
        self.assertFalse(transport._auto_recover)

    def test_local_config_is_not_overwritten_by_example(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'custom.json'
            path.write_text('{"hotkey_key":"option+f9"}', encoding='utf-8')
            self.assertEqual(m.load_config(path)['hotkey_key'], 'option+f9')
            example = Path(temp) / 'voice-config.example.json'
            example.write_text('{"hotkey_key":"f9"}', encoding='utf-8')
            with mock.patch.object(m, 'HERE', Path(temp)):
                self.assertEqual(m.load_config(m.HERE / 'voice-config.json')['hotkey_key'], 'f9')


class UdpIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_udp_to_adpcm_to_stereo_and_key_release(self):
        # Loopback emulator only: no packets to a physical device or broadcast.
        stream = mock.Mock()
        sink = audio.make_audio_sink(m.shared, 'BlackHole', sounddevice([stream]))
        backend = keyboard()
        forwarder = m.MacForwarder(args(), backend, sink)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        provider = mock.Mock(return_value=[])
        transport = UdpTransport(port=port, bind_host='127.0.0.1',
            device_wait_timeout=2, broadcast_targets=provider, auto_recover=False)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.bind(('127.0.0.1', 0))
        peer.setblocking(False)
        loop = asyncio.get_running_loop()
        target = ('127.0.0.1', port)
        try:
            connect = asyncio.create_task(transport.connect('udp://'))
            await asyncio.sleep(.02)
            peer.sendto(b'\x02' + event('device.hello'), target)
            await connect
            provider.assert_called_once_with(port)
            await transport.start_notify(EVENT_UUID, forwarder.on_event)
            await transport.start_notify(AUDIO_UUID, forwarder.on_audio)
            for frame in (b'\x02' + event('voice.start'),
                          b'\x01\x07\x80' + bytes(804),
                          b'\x01\x08\x80' + bytes(804),
                          b'\x01\x08\x80' + bytes(804),
                          b'\x02' + event('voice.end')):
                peer.sendto(frame, target)
            for _ in range(100):
                if forwarder.audio_blocks == 2 and not forwarder.active:
                    break
                await asyncio.sleep(.01)
            self.assertEqual(forwarder.audio_blocks, 2)
            self.assertFalse(forwarder.active)
            self.assertFalse(forwarder.injector._held)
            self.assertGreaterEqual(stream.write.call_count, 2)
            self.assertTrue(all(c.args[0] == bytes(6400) for c in stream.write.call_args_list))
            await transport.write_gatt_char(EVENT_UUID, json.dumps(forwarder.pc_status()).encode())
            packet, _ = await asyncio.wait_for(loop.sock_recvfrom(peer, 2048), 1)
            self.assertEqual(packet[0], 2)
            self.assertEqual(json.loads(packet[1:])['audioReady'], True)
            # A second receiver must fail instead of silently stealing frames.
            second = UdpTransport(port=port, bind_host='127.0.0.1')
            with self.assertRaises(UdpError):
                await second.connect('udp://')
        finally:
            await transport.disconnect()
            forwarder.finish()
            sink.close()
            peer.close()


if __name__ == '__main__':
    unittest.main()
