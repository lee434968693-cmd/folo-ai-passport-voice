# AI Passport Voice with macOS Speech Recognition

This repository is a community fork of
[`manchunx7-bit/folo-ai-passport-voice`](https://github.com/manchunx7-bit/folo-ai-passport-voice).
It adds a direct macOS speech-to-text path that does not require WeChat Input
Method, BlackHole, Codex Dictate, or an ASR API key.

```text
AI Passport microphone
  -> 2.4 GHz Wi-Fi / UDP
  -> macOS client (ADPCM decode)
  -> Apple Speech recognition
  -> text pasted into the focused input field
```

Hold the device's Up button while speaking. Release it to transcribe. After
checking the text, briefly press Down to send Enter.

## Requirements

- Apple Silicon Mac
- macOS 13 or newer
- Native arm64 Python 3.11 or newer
- Xcode Command Line Tools
- Compatible FoloToy AI Passport firmware with the voice app

## Install

From the repository root:

```bash
bash macos/install.command
```

Grant Accessibility to the terminal application used to launch the client, and
grant Speech Recognition permission to:

```text
macos/apple-speech-transcriber/AIPassportSpeech.app
```

Start the client:

```bash
bash macos/start.command
```

To install the background menu-bar client and enable automatic startup after
login:

```bash
bash macos/install-service.command
```

## Privacy and cost

- No OpenAI speech API is used and speech duration does not consume OpenAI
  tokens.
- The default Apple Speech path may send audio-related information to Apple,
  depending on the macOS configuration. Review Apple's Dictation & Privacy
  settings before use.
- Temporary WAV files are created with user-only permissions and deleted after
  transcription.
- Text sent to Codex or another AI app is governed by that app's own usage rules.

See the full Chinese guide:
[macOS direct speech recognition](docs/MAC-LOCAL-SPEECH.zh-CN.md).

## License and attribution

The original project and this fork are distributed under the MIT License in
[LICENSE](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
