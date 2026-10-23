# 参与贡献

感谢改进 AI Passport 随身语音。

## 提交前检查

在项目根目录运行：

```bash
macos/.venv/bin/python3 -m unittest discover -s macos/tests -p 'test_*.py' -v
bash macos/apple-speech-transcriber/build.command
```

涉及 Mac 语音识别的变更，请同时说明：

- Mac 型号、macOS 版本和芯片架构
- 使用 `speech_on_device` 还是 Apple 在线识别
- 是否实际从 AI Passport 出字
- 测试失败时的脱敏错误信息

不要提交以下内容：

- 个人 `voice-config.json`
- 录音、设备 IP、Wi-Fi 密码或局域网拓扑
- token、cookie、账号或任何密钥
- 构建生成的 `.app`、虚拟环境和下载文件

大范围重构请先创建 Issue 说明动机、兼容范围和回退方式。
