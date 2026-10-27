#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"

LABEL="com.folo-aipassport.voice.client"
SUPPORT_ROOT="$HOME/Library/Application Support/AI Passport Voice"
RUNTIME_ROOT="$SUPPORT_ROOT/runtime"
APP_PATH="$RUNTIME_ROOT/macos/AIPassportVoice.app"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"

mkdir -p "$SUPPORT_ROOT" "$RUNTIME_ROOT"
if [ -d "$RUNTIME_ROOT/macos" ]; then
  PREVIOUS_PATH="$SUPPORT_ROOT/previous-$(date '+%Y%m%d-%H%M%S')"
  mv "$RUNTIME_ROOT/macos" "$PREVIOUS_PATH-macos"
  if [ -d "$RUNTIME_ROOT/windows" ]; then
    mv "$RUNTIME_ROOT/windows" "$PREVIOUS_PATH-windows"
  fi
fi
ditto "$PWD" "$RUNTIME_ROOT/macos"
ditto "$PWD/../windows" "$RUNTIME_ROOT/windows"
bash "$RUNTIME_ROOT/macos/client-app/build.command"
mkdir -p "$PLIST_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$APP_PATH/Contents/MacOS/AIPassportVoice</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>LimitLoadToSessionType</key>
  <string>Aqua</string>
  <key>WorkingDirectory</key>
  <string>$RUNTIME_ROOT/macos</string>
  <key>ThrottleInterval</key>
  <integer>5</integer>
</dict>
</plist>
PLIST

plutil -lint "$PLIST_PATH" >/dev/null
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo "后台服务已安装并启动。"
echo "首次使用请把 $APP_PATH 加入“辅助功能”权限。"
