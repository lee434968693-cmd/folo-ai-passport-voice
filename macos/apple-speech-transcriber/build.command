#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"

mkdir -p AIPassportSpeech.app/Contents/MacOS
cp Resources/Info.plist AIPassportSpeech.app/Contents/Info.plist
xcrun swiftc Sources/main.swift \
  -framework AppKit \
  -framework Foundation \
  -framework Speech \
  -o AIPassportSpeech.app/Contents/MacOS/AIPassportSpeech
codesign --force --deep --sign - AIPassportSpeech.app
echo "构建完成：$PWD/AIPassportSpeech.app"
