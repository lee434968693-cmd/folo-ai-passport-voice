#!/bin/bash
set -eu

LABEL="com.folo-aipassport.voice.client"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
if [ -f "$PLIST_PATH" ]; then
  mv "$PLIST_PATH" "$PLIST_PATH.uninstalled"
fi
pkill -x AIPassportVoice >/dev/null 2>&1 || true
echo "后台服务已停止并移除。原配置已重命名为 $PLIST_PATH.uninstalled"
echo "已安装的运行文件保留在 ~/Library/Application Support/AI Passport Voice。"
