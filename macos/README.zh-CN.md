# Apple 芯片 Mac · 微信输入法测试版

本包让设备麦克风通过 Wi-Fi 把声音送入 Mac 的虚拟声卡，并按设备按键触发微信输入法的语音快捷键。文字识别仍由微信输入法完成。本包不包含识别服务、账号、固件或虚拟声卡驱动。

这是源码启动测试包，不是签名的 `.app` 或 `.dmg`。macOS、微信输入法版本和真实 Mac 出字尚未验收；本地验证的是协议、模拟系统接口和异常处理。当前集成固件已使用相同 UDP 协议，这次适配无需重新烧录，也不增加设备端内存占用。

## 1. 准备环境

- Apple 芯片 Mac，使用原生 arm64 的 [Python 3.11 或更新版本](https://www.python.org/downloads/macos/)。不要通过 Rosetta 运行。
- 安装 [BlackHole 官方提供的 2ch 版本](https://github.com/ExistentialAudio/BlackHole)。这是独立的虚拟声卡，需要自行安装；客户端不会替你安装驱动或更改系统音频设置。
- 安装带语音输入功能的 [微信输入法](https://z.weixin.qq.com/)。先用 Mac 自带麦克风确认它能识别，再配置设备音频。
- 设备与 Mac 接入同一可互通的局域网，设备进入“AI语音”。本功能使用 UDP 33333，USB 仅供电，不是 USB 麦克风。

解压后保留 `macos/` 与 `windows/` 的相对位置。后者有三个共享的 Python 协议文件，Mac 不会调用 Windows 的按键接口。

## 2. 安装与配置

1. 打开 `macos/install.command`。首次安装会联网安装 Python 依赖到本目录 `.venv/`，首次创建 `voice-config.json`；已有配置会保留。
2. 查看微信输入法的语音快捷键设置，并修改同目录 `voice-config.json`，让按键和模式完全一致。
3. 微信输入法的语音麦克风选 **BlackHole 2ch**。如果该版本跟随系统默认输入，在“系统设置 → 声音 → 输入”中手动选择 BlackHole 2ch。此时其他跟随默认麦克风的应用也会受影响，用完可改回原来的麦克风。
4. 保持声音**输出**为平时的扬声器或耳机。
5. 在“系统设置 → 隐私与安全性 → 辅助功能”中授权实际运行客户端的宿主（通常为终端；系统也可能列出 Python），授权后关闭并重开客户端。客户端只检查权限，不会自动授予权限。
6. 打开 `diagnose.command`。通过后再打开 `start.command`，保持终端窗口运行。在 macOS 出现本地网络访问提示时允许该客户端访问局域网。

如果双击脚本没有执行，可在终端进入解压目录后运行：

```bash
bash macos/install.command
bash macos/diagnose.command
bash macos/start.command
```

配置示例：

```json
{
  "hotkey_key": "f9",
  "hotkey_mode": "hold",
  "output_substr": "BlackHole 2ch",
  "udp_port": 33333,
  "device_ip": ""
}
```

**F9 是示例，不是已核实的微信输入法默认键。** 只有你的微信输入法支持并设置为 F9 按住说话时才保留此示例。若设置为按一次开始、再按一次结束，模式改为 `tap`；按住开始、松开结束则用 `hold`。支持 `right-shift`、`f9`、`cmd+f9`、`option+f9` 等，执行下面命令可查看键名。Fn/地球键属于待实机验证项，不保证能触发输入法。不同版本允许的快捷键可能不同，无法设置时请先提供输入法版本，不要盲目沿用示例。

```bash
macos/.venv/bin/python3 macos/mac_voice.py --list-keys
macos/.venv/bin/python3 macos/mac_voice.py --list-devices
```

音频方向：**设备麦克风 → Wi-Fi → Mac 客户端 → BlackHole 2ch → 微信输入法**。16 kHz 单声道解码后复制到左右声道，交给 CoreAudio 做必要的采样率转换，不修改系统声卡的全局采样率。音频队列最多五帧，约 500 ms；积压时丢弃旧帧，避免延迟不断增长。

## 3. 在空白文稿里验收

打开文本编辑，切到微信输入法，先不要在聊天发送窗口测试。

1. 按住设备上键，等待输入法语音界面出现，再说“这是 Mac 语音测试”。
2. 松开上键，确认识别结束、出现文字且快捷键没有留在按下状态。
3. 短按下键，确认只插入一次回车。
4. 连续测试三次；再测试按住期间退出设备应用、临时断开 Wi-Fi 和重新进入应用。
5. 使用中断开链路，客户端应停止传音并尝试释放快捷键；音频中断超过约 2.5 秒会先结束当前语音，设备恢复后需重新按键。

`audioReady/hotkeyReady` 仅表示客户端的音频通道和按键权限就绪，不能证明微信输入法的麦克风、快捷键、服务或文字识别正常。权限被撤销后，系统可能拒绝后续事件；客户端会尝试释放并停止，必要时手动松开快捷键或关闭输入法语音面板。

停止客户端用终端 `Ctrl+C`。正常关闭、断线、音频写入失败、权限丢失均有清理路径；强制杀进程或操作系统强制中止无法保证清理执行。

## 常见问题

| 现象 | 排查 |
| --- | --- |
| 安装找不到 Python、架构不符 | 安装原生 arm64 Python 3.11+；重新打开终端，不使用 Rosetta |
| 提示缺少 BlackHole | 安装 2ch 版本；用 `--list-devices` 核对名称；不要选择 Built-in Speakers 作为转发目标 |
| 音频就绪但没有文字 | 确认输入法已切换、语音快捷键和 hold/tap 一致、麦克风选择 BlackHole；先单独验证微信输入法 |
| 快捷键未就绪 | 授权实际运行程序的辅助功能权限后重启；参见 [Apple 权限说明](https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac) |
| 设备一直没有连接 | 同一可互通局域网、无访客网络隔离、允许本地网络访问；只运行一个客户端；按需允许此程序的 UDP 入站，不关闭整套防火墙 |
| 多网卡自动发现不通 | `device_ip` 可填设备当前的局域网 IPv4 地址；地址变化后需更新；客户端也会按实际网卡掩码计算广播并定期刷新 |
| 端口被占用 | 关闭旧的客户端或诊断实例再重试，不能同时运行多个 |
| 设备仍提示检查 VB-CABLE | 现有固件部分提示针对 Windows；Mac 应核对 BlackHole、辅助功能和输入法设置 |

## 验证范围

2026-10-17 在 Windows 原生 Python 3.11 上通过 24 项 Mac 客户端测试与 15 项原 Windows 回归测试。Mac 测试使用模拟 Quartz、模拟声卡以及真实回环 UDP：覆盖按键权限、组合键、部分失败清理、重复包、断线、音频超时、双声道格式、队列上限、驱动失败、广播掩码和完整收发流程。没有采集或上传真实录音，没有向桌面注入真实按键。

测试不代替 Apple 芯片 Mac 上的安装、CoreAudio、系统权限和微信输入法真实出字验收。CI 配置包含 Mac 运行器，执行结果以对应提交的 GitHub Actions 为准；持续集成通过也不能视为微信输入法实机兼容认证。

开发者可运行：

```bash
python3 -m unittest discover -s macos/tests -p 'test_*.py' -v
python3 -m unittest discover -s windows/tests -p 'test_*.py' -v
```

第三方说明：Python 与 sounddevice 按各自许可证使用；Mac 接口通过 [PyObjC](https://pyobjc.readthedocs.io/) 调用。依赖由 pip 单独安装，BlackHole 和微信输入法不随本包分发。识别数据如何处理由输入法的服务与设置决定，本包不承诺离线识别。
