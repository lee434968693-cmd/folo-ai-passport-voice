#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"

mkdir -p ../AIPassportVoice.app/Contents/MacOS
cp Resources/Info.plist ../AIPassportVoice.app/Contents/Info.plist
xcrun swiftc Sources/main.swift \
  -framework AppKit \
  -framework Foundation \
  -o ../AIPassportVoice.app/Contents/MacOS/AIPassportVoice
codesign --force --deep --sign - ../AIPassportVoice.app
echo "构建完成：$PWD/../AIPassportVoice.app"
