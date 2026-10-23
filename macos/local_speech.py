"""Device audio -> temporary WAV -> Apple Speech -> text."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import wave

try:
    import adpcm
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows'))
    import adpcm


SAMPLE_RATE = 16000
MAX_SECONDS = 60


class LocalSpeechError(RuntimeError):
    pass


class AppleSpeechTranscriber:
    """Collect ADPCM blocks and transcribe one utterance with Apple Speech."""

    def __init__(self, app_path, locale='zh-CN', on_device=False, timeout=120):
        self.app_path = Path(app_path)
        self.locale = locale
        self.on_device = on_device
        self.timeout = timeout
        self._buffer = bytearray()
        self._lock = threading.Lock()

    @property
    def ready(self):
        executable = self.app_path / 'Contents' / 'MacOS' / 'AIPassportSpeech'
        return self.app_path.is_dir() and executable.is_file()

    def begin(self):
        with self._lock:
            self._buffer.clear()

    def write_block(self, adpcm_block):
        samples = adpcm.decode_block(adpcm_block)
        pcm = bytearray(len(samples) * 2)
        for index, value in enumerate(samples):
            value = max(-32768, min(32767, int(value)))
            pcm[index * 2] = value & 0xFF
            pcm[index * 2 + 1] = (value >> 8) & 0xFF
        max_bytes = SAMPLE_RATE * 2 * MAX_SECONDS
        with self._lock:
            self._buffer.extend(pcm)
            if len(self._buffer) > max_bytes:
                del self._buffer[:-max_bytes]

    def finish_capture(self):
        with self._lock:
            pcm = bytes(self._buffer)
            self._buffer.clear()
        return pcm

    def cancel_capture(self):
        with self._lock:
            self._buffer.clear()

    def transcribe(self, pcm):
        if len(pcm) < SAMPLE_RATE:
            raise LocalSpeechError('语音太短，没有可识别的音频')
        if not self.ready:
            raise LocalSpeechError(f'语音识别应用不存在：{self.app_path}')

        wav_fd, wav_path = tempfile.mkstemp(prefix='ai-passport-', suffix='.wav')
        result_fd, result_path = tempfile.mkstemp(prefix='ai-passport-', suffix='.json')
        os.close(result_fd)
        try:
            os.fchmod(wav_fd, 0o600)
            with os.fdopen(wav_fd, 'wb') as stream:
                wav_fd = -1
                with wave.open(stream, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(SAMPLE_RATE)
                    wav.writeframes(pcm)
            args = [
                'open', '-g', '-W', '-n', '-a', str(self.app_path), '--args',
                f'--audio={wav_path}',
                f'--locale={self.locale}',
                f'--output={result_path}',
            ]
            if self.on_device:
                args.append('--on-device')
            completed = subprocess.run(
                args, capture_output=True, text=True, timeout=self.timeout
            )
            if completed.returncode:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise LocalSpeechError(detail or 'Apple 语音识别启动失败')
            try:
                payload = json.loads(Path(result_path).read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as error:
                raise LocalSpeechError(f'Apple 语音识别没有返回有效结果：{error}') from error
            if payload.get('error'):
                raise LocalSpeechError(str(payload['error']))
            text = str(payload.get('text') or '').strip()
            if not text:
                raise LocalSpeechError('Apple 语音识别没有返回文字')
            return text
        except subprocess.TimeoutExpired as error:
            raise LocalSpeechError('Apple 语音识别超时') from error
        finally:
            if wav_fd >= 0:
                os.close(wav_fd)
            for path in (wav_path, result_path):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
