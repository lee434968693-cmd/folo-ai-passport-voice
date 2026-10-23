# macOS 直接语音识别版

本版本在保留原有 Mac 微信输入法模式的基础上，增加一条不依赖微信输入法、
BlackHole 或 Codex Dictate 的识别链路：

```text
AI Passport 麦克风
        │ 2.4 GHz Wi-Fi / UDP 33333
        ▼
macOS 客户端
        │ 16 kHz ADPCM → WAV（临时文件，识别后立即删除）
        ▼
Apple Speech 语音识别
        │ 最终文字
        ▼
当前获得焦点的输入框
```

按住设备上键说话，松开后等待文字；核对文字后短按下键发送回车。

## 适用范围

- Apple 芯片 Mac
- macOS 13 或更新版本
- 原生 arm64 Python 3.11 或更新版本
- Swift 工具链（Xcode Command Line Tools）
- 同款 ESP32-C3 / 8 MB / ES8311 AI Passport，固件可打开“随身语音”

默认模式不需要 BlackHole、VB-CABLE、微信输入法或任何 ASR API Key。

## Token 与隐私

- 本项目不会调用 OpenAI 语音接口，不按说话时长产生 OpenAI Token 或 API 费用。
- 默认 `"speech_on_device": false`，音频由 Apple Speech 处理；在部分系统配置下，
  录音信息可能发送给 Apple。使用前请阅读系统“听写与隐私”说明。
- 临时 WAV 仅写入系统临时目录，权限设为当前用户可读写，识别结束后立即删除。
- 识别结果发送给 Codex、ChatGPT 或其他目标软件后，仍按该软件自身的用量规则计算。

## 安装

在解压后的完整项目根目录执行：

```bash
bash macos/install.command
```

脚本会：

1. 检查 Apple 芯片与 Python 架构。
2. 在 `macos/.venv` 中安装 Python 依赖。
3. 使用 Swift 构建 `macos/apple-speech-transcriber/AIPassportSpeech.app`。
4. 在没有个人配置时创建 `macos/voice-config.json`。

如果提示找不到 Swift 工具链，请先从 Apple 官方渠道安装
Xcode Command Line Tools，然后重新运行安装脚本。

## 系统权限

打开“系统设置 → 隐私与安全性”：

| 权限 | 授权对象 | 用途 |
| --- | --- | --- |
| 辅助功能 | 实际启动客户端的终端、iTerm 或 VS Code | 粘贴识别文字、发送回车 |
| 语音识别 | `AIPassportSpeech.app` | 将设备语音转成文字 |

首次识别时系统可能弹出语音识别授权。若没有弹窗，可在“语音识别”权限页中
添加：

```text
macos/apple-speech-transcriber/AIPassportSpeech.app
```

授权后完全退出并重新打开终端，再启动客户端。

## 配置

默认 [voice-config.example.json](../macos/voice-config.example.json)：

```json
{
  "transcription_mode": "apple-speech",
  "speech_locale": "zh-CN",
  "speech_on_device": false,
  "hotkey_key": "f9",
  "hotkey_mode": "hold",
  "output_substr": "BlackHole 2ch",
  "udp_port": 33333,
  "device_ip": ""
}
```

Apple Speech 模式会忽略 `hotkey_key`、`hotkey_mode` 和 `output_substr`。
保留这些字段是为了可切回原来的微信输入法模式。

可选语言示例：

- 普通话：`zh-CN`
- 粤语：`yue-Hant-HK`（系统是否支持以实际设备为准）
- 英语：`en-US`

`"speech_on_device": true` 要求系统已经安装对应语言的本地识别模型；未安装时
会直接报错，不会静默切换到 Apple 在线识别。

## 启动与使用

在项目根目录执行：

```bash
bash macos/start.command
```

确认设备与 Mac 在同一可互通的局域网，并进入设备的“AI语音”页面。

1. 点击目标软件的文字输入框，让光标出现。
2. 按住设备上键，开始说话。
3. 松开上键。
4. 等待客户端显示“已填入文字”。
5. 核对文字，短按设备下键发送回车。

不要在录音结束前按设备下键。客户端会等待识别完成，但最稳妥的做法是看到
文字后再发送。

## 诊断

```bash
macos/.venv/bin/python3 macos/mac_voice.py --diagnose
```

应看到：

- 辅助功能权限正常
- UDP 33333 可监听
- Apple Speech 识别辅助程序存在

诊断不会代替真实语音测试。请在普通文本编辑器中先验证，再用于聊天软件。

## 常见问题

### 有文字但填到了错误窗口

识别期间不要切换窗口。辅助程序在后台运行，但最终文字会粘贴到当前获得焦点的
输入框。

### 语音识别没有授权

到“系统设置 → 隐私与安全性 → 语音识别”，允许 `AIPassportSpeech.app`。

### 首次识别很慢

首次启动语音识别服务和加载语言模型可能需要数秒。后续通常会更快。

### 临时音频是否会被保存

不会长期保存。客户端写入权限受限的临时 WAV，读取识别结果后立即删除。

### 如何切回微信输入法 + BlackHole

把 `macos/voice-config.json` 中的 `transcription_mode` 改为 `hotkey`，并参照
[原 Mac 教程](../macos/README.zh-CN.md) 配置。
