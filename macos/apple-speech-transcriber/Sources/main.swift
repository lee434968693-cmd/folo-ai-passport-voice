import AppKit
import Foundation
import Speech

struct Output: Codable {
    let text: String
    let locale: String
    let onDevice: Bool
}

func fail(_ message: String, code: Int32 = 1) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    if let path = argument("--output", "-output") {
        let payload = ["error": message]
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) {
            try? data.write(to: URL(fileURLWithPath: path), options: .atomic)
        }
    }
    exit(code)
}

func log(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

func argument(_ names: String...) -> String? {
    for name in names {
        if let index = CommandLine.arguments.firstIndex(of: name),
           CommandLine.arguments.indices.contains(index + 1) {
            return CommandLine.arguments[index + 1]
        }
        if let value = CommandLine.arguments.first(where: { $0.hasPrefix(name + "=") }) {
            return String(value.dropFirst(name.count + 1))
        }
    }
    return nil
}

guard let audioPath = argument("--audio", "-audio") else {
    fail("缺少 --audio 音频文件参数")
}
let localeIdentifier = argument("--locale", "-locale") ?? "zh-CN"
let onDeviceOnly = CommandLine.arguments.contains("--on-device")
let outputPath = argument("--output", "-output")
let audioURL = URL(fileURLWithPath: audioPath)

guard FileManager.default.fileExists(atPath: audioURL.path) else {
    fail("音频文件不存在：\(audioURL.path)")
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)

log("正在请求语音识别权限")
var authorizationStatus = SFSpeechRecognizer.authorizationStatus()
if authorizationStatus == .notDetermined {
    var authorizationFinished = false
    SFSpeechRecognizer.requestAuthorization { status in
        authorizationStatus = status
        authorizationFinished = true
    }
    let authorizationDeadline = Date().addingTimeInterval(30)
    while !authorizationFinished && Date() < authorizationDeadline {
        RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1))
    }
    guard authorizationFinished else {
        fail("等待语音识别授权超时")
    }
}

guard authorizationStatus == .authorized else {
    fail("语音识别未获授权，状态码：\(authorizationStatus.rawValue)")
}
log("语音识别权限正常")

guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: localeIdentifier)),
      recognizer.isAvailable else {
    fail("当前系统无法使用 \(localeIdentifier) 语音识别")
}

if onDeviceOnly && !recognizer.supportsOnDeviceRecognition {
    fail("当前系统未安装 \(localeIdentifier) 的本地语音识别模型")
}

let request = SFSpeechURLRecognitionRequest(url: audioURL)
request.shouldReportPartialResults = false
request.taskHint = SFSpeechRecognitionTaskHint.dictation
request.addsPunctuation = true
request.requiresOnDeviceRecognition = onDeviceOnly

var finalText: String?
var recognitionError: Error?
var recognitionFinished = false

let task = recognizer.recognitionTask(with: request) { result, error in
    if let result, result.isFinal {
        finalText = result.bestTranscription.formattedString
        recognitionFinished = true
    } else if let error {
        recognitionError = error
        recognitionFinished = true
    }
}

let recognitionDeadline = Date().addingTimeInterval(90)
while !recognitionFinished && Date() < recognitionDeadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1))
}

guard recognitionFinished else {
    task.cancel()
    fail("语音识别超时")
}

if let recognitionError {
    fail("语音识别失败：\(recognitionError.localizedDescription)")
}

guard let text = finalText?.trimmingCharacters(in: .whitespacesAndNewlines),
      !text.isEmpty else {
    fail("没有识别到文字")
}

let output = Output(
    text: text,
    locale: localeIdentifier,
    onDevice: request.requiresOnDeviceRecognition
)
let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]
let data = try encoder.encode(output)
if let outputPath {
    try data.write(to: URL(fileURLWithPath: outputPath), options: .atomic)
} else {
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
}
