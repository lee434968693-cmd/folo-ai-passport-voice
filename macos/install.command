#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
trap 'result=$?; if [ "$result" -ne 0 ]; then echo "安装未完成，请查看上方错误。"; fi; if [ -t 0 ]; then read -r -p "按回车关闭…" _reply || true; fi' EXIT
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo "此测试包需要 Apple 芯片 Mac，请勿通过 Rosetta 启动。"
  exit 1
fi
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3.13 python3.12 python3.11 /usr/local/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import platform, sys; raise SystemExit(0 if sys.version_info >= (3, 11) and platform.machine() == "arm64" else 1)' 2>/dev/null; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "请安装原生 arm64 Python 3.11 或更新版本。"
  exit 1
fi
if [ ! -x .venv/bin/python3 ]; then
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python3 -m pip install -r requirements.txt
if command -v xcrun >/dev/null 2>&1 && xcrun --find swiftc >/dev/null 2>&1; then
  bash apple-speech-transcriber/build.command
  bash client-app/build.command
else
  echo "未找到 Swift 工具链；语音识别辅助程序和后台客户端未构建。"
  echo "请从 App Store 安装 Xcode Command Line Tools 后重新运行本脚本。"
fi
if [ ! -f voice-config.json ]; then
  cp voice-config.example.json voice-config.json
fi
echo "依赖安装完成。请按 README 授权辅助功能与语音识别，再运行 diagnose.command。"
