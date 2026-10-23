# AI Passport 随身语音

按住设备上键说话，松开结束识别，核对文字后短按下键回车。这个项目把 AI Passport 用作电脑的无线麦克风与语音快捷键。

本分支新增 **Mac 直接语音识别模式**：设备音频由 macOS 客户端收集并交给
Apple Speech，识别文字自动粘贴到当前输入框。该模式不需要微信输入法、
BlackHole、Codex Dictate 或 ASR API Key，也不按说话时长消耗 OpenAI Token。
Windows 继续提供原有的 VB-CABLE/输入法方案。

Mac 可安装为登录后自动启动的后台菜单栏客户端，日常不需要打开终端。

**本仓库只开源随身语音功能，不含整机源码或可刷写固件。** 固件由维护者在 [FoloToy 口袋百宝箱玩法页面](https://ai-passport.folotoy.cn/plays/438/) 发布。该页面若暂未提供包含随身语音的版本，请等待更新；不要把本仓库 Source code ZIP 当固件。

## 选择你的电脑

| 平台 | 安装与配置教程 | 软件与启动方式 |
| --- | --- | --- |
| **macOS · Apple 芯片** | **[Mac 直接语音识别教程](docs/MAC-LOCAL-SPEECH.zh-CN.md)**：Python、Swift、权限、识别、首次出字及排障 | 完整源码；原生 arm64 Python 3.11+；`bash macos/install.command` 后运行 `bash macos/start.command` |
| **Windows 10/11 x64** | **[Windows 完整配置教程](docs/QUICKSTART.zh-CN.md)**：应用包、VB-CABLE、输入法、映射和记事本验收 | [Releases](https://github.com/manchunx7-bit/folo-ai-passport-voice/releases) 下载 `ai-passport-voice-app-0.2.0.zip`；解压后双击 `windows/start.cmd` |

Mac 当前没有签名分发的 `.dmg`；Intel Mac 和 Rosetta 下的 x86 Python 不支持。
Mac 请保留完整源码中 `macos/` 与 `windows/` 的相对位置。

### 两个平台共用的准备

使用同款 ESP32-C3 / 8 MB / ES8311 的 FoloToy AI Passport，安装官网玩法页提供的、包含“随身语音”的固件；设备已能打开此功能就跳过刷写。本次 Mac 适配复用现有协议，无需为它重新烧录。

设备接入 2.4 GHz Wi-Fi，电脑和设备在同一可互通局域网，使用 UDP 33333。
电脑可通过同一路由器的网线或 5 GHz Wi-Fi 接入。USB 不会自动把设备变成
USB 麦克风，不需要蓝牙配对。

### 音频方向别选反

Mac 直接识别：

```text
设备麦克风 → Wi-Fi UDP → Mac 客户端 → Apple Speech → 当前输入框
```

Windows 兼容模式：

```text
设备麦克风 → Wi-Fi UDP → Windows 转发器 → VB-CABLE → 输入法 → 当前输入框
```

| 设置位置 | macOS 直接识别 | Windows 兼容模式 |
| --- | --- | --- |
| 转发器音频出口 | 不经过虚拟声卡 | **CABLE Input** |
| 输入法麦克风 | 不使用输入法 | **CABLE Output** |
| 系统默认输入 | 不影响 | 按教程选 CABLE Output |
| 系统默认输出 | 保持自己的扬声器 / 耳机 | 保持自己的扬声器 / 耳机 |

### 按键与首次验收

- 按住上键：开始录音。
- 松开上键：结束录音并开始识别。
- 短按下键：发送 Enter；当前软件决定它是换行还是发送消息。先在 Mac 文本编辑或 Windows 记事本试，不要在重要聊天窗口直接测试。
- 长按确定：退出设备应用。

Mac 直接识别模式不需要配置任何输入法快捷键。Windows 和原 Mac 兼容模式仍要求
输入法快捷键与 `hotkey_key`、`hotkey_mode` 一致。

## 源码边界

| 目录 | 内容 |
| --- | --- |
| `windows/` | 可运行的 Windows 转发器、ADPCM 解码、UDP 通道、诊断与测试 |
| `macos/` | Apple 芯片 Mac 客户端、Apple Speech 识别辅助程序、启动脚本、诊断与测试 |
| `device/main/apps/voice/` | 本功能的设备端状态机、协议、录音生命周期、传输和界面业务代码 |
| `device/tests/` | 语音状态机和界面数学的可独立运行测试 |
| `docs/` | 使用、排错、固件入口、开发与底层接口适配说明 |

不包含首页/名片、收音机、小智、游戏、秒表、整机启动器、设置页、BSP 实现、共享字体或整机历史。设备端是**功能模块源码**，不是单独可刷写的 ESP-IDF 工程；开发者需按 [适配说明](docs/PORTING.zh-CN.md) 提供宿主接口。Windows 程序与纯逻辑测试可独立运行。

## 文档

- [macOS 直接语音识别教程](docs/MAC-LOCAL-SPEECH.zh-CN.md)
- [macOS 原微信输入法 / BlackHole 教程](macos/README.zh-CN.md)
- [English README](README.en.md)
- [Windows 完整配置教程](docs/QUICKSTART.zh-CN.md)
- [按平台查找故障排查](docs/TROUBLESHOOTING.zh-CN.md)
- [用本地 Codex 辅助配置：Mac / Windows](docs/CODEX_SETUP.zh-CN.md)
- [官网固件与刷写注意](docs/FIRMWARE.zh-CN.md)
- [源码运行与测试](docs/DEVELOPMENT.zh-CN.md)
- [验证记录及限制](docs/VALIDATION.md)
- [第三方来源](THIRD_PARTY_NOTICES.md)

<a id="codex-setup"></a>
## 让本地 Codex 帮忙配置

在解压后的**完整项目目录**打开这台电脑上的本地 Codex，按平台复制。它需要能访问本地文件与终端；系统授权、重启和实际说话需要你参与。

### macOS

```text
请阅读 README.md 和 docs/MAC-LOCAL-SPEECH.zh-CN.md，帮助我配置 AI Passport
macOS 直接语音识别版。先核对 Apple 芯片、macOS、Python 3.11+ 和 Swift 工具链，
完整保留 macos 与 windows 目录；已有语音配置先备份。
运行 macos/install.command 安装依赖并构建 AIPassportSpeech.app。核对终端辅助
功能权限与 AIPassportSpeech.app 的语音识别权限，不关闭系统安全保护。
默认 transcription_mode 为 apple-speech，不需要微信输入法或 BlackHole。用
macos/.venv/bin/python3 macos/mac_voice.py --diagnose 检查后启动
macos/start.command。
最后让我在文本编辑里对设备说话，确认松开后文字出现、下键只回车一次。诊断
通过不能代替真实语音验收。不要上传个人配置、录音或密钥。
```

### Windows

```text
先阅读 README.md 和 docs/QUICKSTART.zh-CN.md。只帮助我配置随身语音电脑端，不要重建或公开整机源码。固件从官网玩法页获取，不要把 Source code ZIP 当固件。
先运行 windows/AI-Passport-Voice.exe --diagnose，核对 VB-CABLE 两端、UDP 33333 和快捷键。已有配置先备份；我的输入法开始/结束快捷键和 hold/tap 模式需要按真实设置核对。
修改默认麦克风、安装驱动或开放防火墙前说明影响。不要关闭整套防火墙，也不要把系统声音输出改成 CABLE Input。
最后让我在记事本亲自说话，确认松开结束、文字出现、下键换行。未实际验证的环节明确说明，不自动把环境声音发到云端。
```

详见 [辅助配置说明](docs/CODEX_SETUP.zh-CN.md)。个人配置、录音与输入法账号不要提交到 GitHub。本项目不提供识别账号或 ASR 服务，也不承诺所有输入法版本兼容。
