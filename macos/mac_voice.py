#!/usr/bin/env python3
"""Apple Silicon client; reuses the Wi-Fi/ADPCM device protocol."""
import argparse
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import platform
import signal
import socket
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'windows'))
import hotkey_forwarder as shared
from udp_transport import UdpTransport
from mac_keys import CODES, MacKeyInjector, QuartzKeyboard, KeyErrorMac, resolve_key_spec
from mac_audio import make_audio_sink, coreaudio_options
from mac_network import broadcast_targets
from local_speech import AppleSpeechTranscriber, LocalSpeechError
from mac_text import AppBridgeTextInjector, MacTextInjector, TextInjectionError


class MacForwarder(shared.Forwarder):
    def __init__(self, args, keyboard, sink, transcriber=None, text_injector=None):
        # Avoid constructing any Windows key injector or audio endpoint.
        self.args = args
        self.injector = MacKeyInjector(args.key, args.mode, keyboard)
        self.enter_injector = MacKeyInjector('enter', 'tap', keyboard)
        self.sink = sink
        self.transcriber = transcriber
        self.text_injector = text_injector
        self.local_mode = transcriber is not None
        self.input_bridge = getattr(text_injector, 'uses_app_bridge', False) is True
        self.transcribing = False
        self.pending_enter = False
        self.loop = None
        self.audio_route_label = 'Apple Speech' if self.local_mode else 'BlackHole'
        self.audio_blocks = 0
        self.active = False
        self.last_audio_at = 0.0
        self.last_seq = None
        self.last_enter_at = float('-inf')

    def make_transport(self):
        return UdpTransport(port=self.args.port, device_wait_timeout=10 ** 9,
            device_ip=self.args.device_ip, auto_recover=False, broadcast_targets=broadcast_targets)

    def pc_status(self):
        audio_ready = bool(self.transcriber and self.transcriber.ready) if self.local_mode \
            else bool(self.sink and self.sink.enabled)
        input_ready = self.text_injector.ready if self.input_bridge else self.injector.ready
        return {'type': 'pc.status', 'audioReady': audio_ready,
                'hotkeyReady': bool(input_ready)}

    def finish(self, drain=False):
        if self.local_mode:
            self.active = False
            if self.transcriber:
                self.transcriber.cancel_capture()
            return
        try:
            super().finish(drain=drain)
        except KeyErrorMac as error:
            print(f'[key] 释放或结束快捷键失败：{error}', file=sys.stderr)

    def _input_ready(self):
        return self.text_injector.ready if self.input_bridge else self.injector.ready

    def _send_enter(self):
        if self.input_bridge:
            self.text_injector.press_enter()
        else:
            self.enter_injector.click()

    def _transcription_done(self, text, error):
        self.transcribing = False
        if error:
            print(f'[speech] 识别失败：{error}', file=sys.stderr)
            self.pending_enter = False
            return
        try:
            self.text_injector.insert(text)
            print(f'[speech] 已填入文字：{text}')
        except (TextInjectionError, KeyErrorMac) as injection_error:
            print(f'[speech] 填字失败：{injection_error}', file=sys.stderr)
            self.pending_enter = False
            return
        if self.pending_enter:
            self.pending_enter = False
            time.sleep(0.12)
            try:
                self._send_enter()
            except KeyErrorMac as enter_error:
                print(f'[speech] 回车发送失败：{enter_error}', file=sys.stderr)

    def _start_transcription(self):
        pcm = self.transcriber.finish_capture()
        if not pcm:
            print('[speech] 没有收到可识别的语音', file=sys.stderr)
            return
        self.transcribing = True
        print('[speech] 正在识别…')

        def worker():
            text = None
            error = None
            try:
                text = self.transcriber.transcribe(pcm)
            except (LocalSpeechError, OSError, ValueError) as exc:
                error = exc
            if self.loop is not None:
                self.loop.call_soon_threadsafe(self._transcription_done, text, error)
            else:
                self._transcription_done(text, error)

        threading.Thread(target=worker, name='apple_speech', daemon=True).start()

    def _on_local_event(self, event):
        name = event.get('event', '')
        if name == 'voice.start':
            if self.active or self.transcribing:
                print('[speech] 上一次识别尚未完成，忽略新的录音')
                return
            if not self.transcriber.ready:
                print('[speech] Apple 语音识别应用未构建完成', file=sys.stderr)
                return
            print('[evt] 设备开始说话(voice.start)')
            self.audio_blocks = 0
            self.last_seq = None
            self.last_audio_at = time.monotonic()
            self.transcriber.begin()
            self.active = True
        elif name == 'voice.end':
            if not self.active:
                return
            self.active = False
            print(f'[evt] 设备结束说话(voice.end),收到音频块={self.audio_blocks}')
            self._start_transcription()
        elif name == 'key.action' and event.get('action') == 'enter':
            now = time.monotonic()
            if now - self.last_enter_at < shared.ENTER_DEBOUNCE_SECONDS:
                print('[evt] 忽略重复的下键回车')
                return
            self.last_enter_at = now
            if self.transcribing:
                self.pending_enter = True
                print('[evt] 正在识别，文字填入后将自动回车')
            else:
                self._send_enter()
        elif name == 'device.hello':
            print('[evt] 设备上线(device.hello)')

    def on_event(self, payload):
        try:
            event = json.loads(payload.decode('utf-8').strip())
            if not isinstance(event, dict):
                return
            if (event.get('event') == 'voice.start' or
                    event.get('event') == 'key.action') and not self._input_ready():
                self.finish()
                return
            if self.local_mode:
                self._on_local_event(event)
                return
            super().on_event(payload)
        except KeyErrorMac as error:
            self.finish()
            print(f'[key] Mac 快捷键未就绪：{error}', file=sys.stderr)
        except (ValueError, UnicodeDecodeError):
            return

    def check_health(self, now=None):
        if self.active and not self._input_ready():
            self.finish()
        if self.local_mode:
            now = time.monotonic() if now is None else now
            if self.active and now - self.last_audio_at > 2.5:
                print('[link] 语音通道中断，停止本次录音')
                self.finish()
            return
        super().check_health(now)

    def on_audio(self, payload):
        if self.active and not self._input_ready():
            self.finish()
            return
        if self.local_mode:
            if self.active and len(payload) == 806 and payload[1] == 0x80:
                seq = payload[0]
                if self.last_seq is not None and not 0 < ((seq - self.last_seq) & 255) < 128:
                    return
                self.last_seq = seq
                self.last_audio_at = time.monotonic()
                self.transcriber.write_block(payload[2:])
                self.audio_blocks += 1
                if self.audio_blocks == 1:
                    print('[audio] 已收到设备首个音频块，正在交给 Apple Speech')
            return
        super().on_audio(payload)

    async def run(self):
        self.loop = asyncio.get_running_loop()
        await super().run()


def load_config(path):
    source = Path(path)
    if not source.exists() and source == HERE / 'voice-config.json':
        source = HERE / 'voice-config.example.json'
    with source.open(encoding='utf-8-sig') as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError('配置必须是 JSON 对象')
    return config


def diagnose(args, keyboard_factory=QuartzKeyboard, sd=None):
    print('AI Passport Mac 客户端诊断（不采音、不修改音频设置）')
    print('系统：', platform.mac_ver()[0] or sys.platform, '架构：', platform.machine())
    failures = 0
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or sys.version_info < (3, 11):
        print('[FAIL] 此测试包面向 Apple 芯片，请使用原生 arm64 Python 3.11+。')
        failures += 1
    try:
        keyboard = keyboard_factory()
        if not keyboard.ready:
            raise RuntimeError('请在隐私与安全→辅助功能授权实际启动程序，然后重开客户端')
        if args.transcription == 'apple-speech':
            print('[OK] 辅助功能权限；用于粘贴文字和发送回车。')
        else:
            print('[OK] 按键权限；仍需核对微信输入法的语音快捷键。')
    except Exception as error:
        print('[FAIL]', error)
        failures += 1
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', args.port))
        print(f'[OK] UDP {args.port} 可绑定；这不证明局域网权限或设备链路已通。')
    except OSError as error:
        print('[FAIL] UDP 端口不可用；请只运行一个转发程序：', error)
        failures += 1
    if args.transcription != 'apple-speech':
        try:
            module = sd
            if module is None:
                import sounddevice as module
            devices = module.query_devices()
            candidates = [(i, d) for i, d in enumerate(devices)
                if args.output_substr.lower() in d['name'].lower() and d['max_output_channels'] >= 2]
            valid = []
            for index, device in candidates:
                if device['max_input_channels'] < 2:
                    continue
                try:
                    module.check_output_settings(device=index, samplerate=16000, channels=2,
                        dtype='int16', extra_settings=coreaudio_options(module))
                    valid.append(device['name'])
                except Exception:
                    pass
            if not valid:
                raise RuntimeError('未找到支持格式的双向虚拟声卡，请单独安装 BlackHole 2ch')
            print('[OK] 可用虚拟声卡：', ', '.join(valid))
        except Exception as error:
            print('[FAIL] 音频：', error)
            failures += 1
    if args.transcription == 'apple-speech':
        transcriber = AppleSpeechTranscriber(
            args.speech_app, args.speech_locale, args.speech_on_device
        )
        if transcriber.ready:
            print('[OK] Apple Speech 识别辅助程序；首次使用需允许“语音识别”权限。')
        else:
            print('[FAIL] 未找到 Apple Speech 识别辅助程序；请先运行 install.command。')
            failures += 1
        print('此模式不依赖微信输入法或 BlackHole；识别文字会粘贴到当前输入框。')
    else:
        print('诊断通过不代表微信输入法出字成功；请在空白文稿实测按下、说话、松开。')
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description='AI Passport · Apple 芯片 Mac 语音客户端')
    parser.add_argument('--config', default=str(HERE / 'voice-config.json'))
    parser.add_argument('--key')
    parser.add_argument('--mode', choices=['hold', 'tap'])
    parser.add_argument('--port', type=int)
    parser.add_argument('--device-ip')
    parser.add_argument('--output-substr')
    parser.add_argument('--transcription', choices=['hotkey', 'apple-speech'])
    parser.add_argument('--speech-app')
    parser.add_argument('--speech-locale')
    parser.add_argument('--speech-on-device', action='store_true', default=None)
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--list-keys', action='store_true')
    parser.add_argument('--list-devices', action='store_true')
    args = parser.parse_args()
    parent_pid = os.environ.get('AI_PASSPORT_PARENT_PID')
    if parent_pid:
        try:
            expected_parent = int(parent_pid)
        except ValueError:
            parser.error('AI_PASSPORT_PARENT_PID 无效')

        def watch_parent():
            while os.getppid() == expected_parent:
                time.sleep(2)
            print('[lifecycle] 菜单栏应用已退出，停止客户端', file=sys.stderr)
            os._exit(0)

        threading.Thread(target=watch_parent, name='parent_watchdog', daemon=True).start()

    if args.list_keys:
        print(' '.join(sorted(CODES)))
        print('修饰键：ctrl/shift/cmd/option；与微信输入法设置保持一致。Fn 为待实测兼容项。')
        return 0
    try:
        config = load_config(args.config)
        args.key = args.key or config.get('hotkey_key') or 'f9'
        args.mode = args.mode or config.get('hotkey_mode') or 'hold'
        args.port = args.port if args.port is not None else int(config.get('udp_port', 33333))
        args.device_ip = args.device_ip if args.device_ip is not None else str(config.get('device_ip') or '')
        args.output_substr = args.output_substr or config.get('output_substr') or 'BlackHole 2ch'
        args.transcription = args.transcription or config.get('transcription_mode') or 'hotkey'
        args.speech_app = args.speech_app or config.get('speech_app') or str(
            HERE / 'apple-speech-transcriber' / 'AIPassportSpeech.app')
        args.speech_locale = args.speech_locale or config.get('speech_locale') or 'zh-CN'
        if args.speech_on_device is None:
            args.speech_on_device = bool(config.get('speech_on_device', False))
        resolve_key_spec(args.key)
        if args.transcription not in ('hotkey', 'apple-speech'):
            raise ValueError('转写模式必须是 hotkey 或 apple-speech')
        if args.mode not in ('hold', 'tap') or not 1 <= args.port <= 65535:
            raise ValueError('快捷键模式或 UDP 端口无效')
        if not isinstance(args.output_substr, str) or not args.output_substr.strip():
            raise ValueError('虚拟声卡名称不能为空')
        if args.device_ip:
            ipaddress.IPv4Address(args.device_ip)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    if args.diagnose:
        return diagnose(args)
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or sys.version_info < (3, 11):
        parser.error('请在 Apple 芯片 Mac 的原生 arm64 Python 3.11+ 中运行')
    if args.list_devices:
        try:
            import sounddevice as sd
            for i, d in enumerate(sd.query_devices()):
                print(i, d['name'], '输入', d['max_input_channels'], '输出', d['max_output_channels'])
        except (ImportError, OSError) as error:
            parser.error(f'无法枚举声卡，请先运行 install.command：{error}')
        return 0
    try:
        keyboard = QuartzKeyboard()
    except ImportError as error:
        parser.error(f'缺少 Mac 依赖，请先运行 install.command：{error}')
    app_bridge = os.environ.get('AI_PASSPORT_APP_BRIDGE') == '1'
    if not app_bridge and not keyboard.ready:
        keyboard.request_permission()
    transcriber = None
    sink = None
    text_injector = None
    if args.transcription == 'apple-speech':
        transcriber = AppleSpeechTranscriber(
            args.speech_app, args.speech_locale, args.speech_on_device
        )
        if not transcriber.ready:
            parser.error('Apple Speech 识别辅助程序未构建；请先运行 macos/install.command')
        if app_bridge:
            text_injector = AppBridgeTextInjector()
        else:
            text_injector = MacTextInjector(keyboard)
    else:
        sink = make_audio_sink(shared, args.output_substr)
    forwarder = MacForwarder(
        args, keyboard, sink, transcriber=transcriber, text_injector=text_injector
    )
    print('Mac 客户端：设备与 Mac 连接同一局域网，进入设备的 AI语音。')
    if transcriber:
        print(f'语音识别：Apple Speech（{args.speech_locale}），无需微信输入法或虚拟声卡。')
        print('按住设备上键说话，松开后识别；文字会粘贴到当前输入框。按 Ctrl+C 停止。')
    else:
        print(f'快捷键 {args.key} / {args.mode}，请先在微信输入法里设为一致。')
        print('微信输入法的语音麦克风选择 BlackHole 2ch；如只跟随系统输入，需自行在系统声音输入中选择。')
        print('本程序不更改默认扬声器或麦克风。按 Ctrl+C 停止。')
    if not app_bridge and not keyboard.ready:
        print('[权限未就绪] 请运行 diagnose.command，授权后重开。')
    def stop_signal(_signum, _frame):
        raise KeyboardInterrupt
    for name in ('SIGTERM', 'SIGHUP'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop_signal)
    try:
        asyncio.run(forwarder.run())
    except KeyboardInterrupt:
        pass
    finally:
        forwarder.finish()
        if sink:
            sink.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
