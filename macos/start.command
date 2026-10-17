#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
trap 'result=$?; if [ "$result" -ne 0 ]; then echo "启动失败，请查看上方错误。"; fi; if [ -t 0 ]; then read -r -p "按回车关闭…" _reply || true; fi' EXIT
if [ ! -x .venv/bin/python3 ]; then
  echo "请先运行 install.command。"
  exit 1
fi
.venv/bin/python3 mac_voice.py "$@"
