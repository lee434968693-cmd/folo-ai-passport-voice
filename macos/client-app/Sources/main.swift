import AppKit
import ApplicationServices
import Darwin
import Foundation

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var statusMenuItem: NSMenuItem!
    private var process: Process?
    private var stopping = false
    private var logHandle: FileHandle?
    private var logURL: URL!
    private var pythonURL: URL!
    private var scriptURL: URL!
    private var runToken = UUID()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.accessory)
        resolvePaths()
        createLogFile()
        createMenu()
        registerAppBridge()
        if !AXIsProcessTrusted() {
            let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
            _ = AXIsProcessTrustedWithOptions(options)
            writeLog("辅助功能权限未就绪，已请求系统授权")
        }
        startClient()
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopping = true
        stopClient()
    }

    private func resolvePaths() {
        let appURL = Bundle.main.bundleURL
        let macosURL = appURL.deletingLastPathComponent()
        let rootURL = macosURL.deletingLastPathComponent()
        pythonURL = macosURL.appendingPathComponent(".venv/bin/python3")
        scriptURL = macosURL.appendingPathComponent("mac_voice.py")
        let logsURL = rootURL.appendingPathComponent("logs", isDirectory: true)
        try? FileManager.default.createDirectory(at: logsURL, withIntermediateDirectories: true)
        logURL = logsURL.appendingPathComponent("client.log")
    }

    private func createLogFile() {
        if let attributes = try? FileManager.default.attributesOfItem(atPath: logURL.path),
           let size = attributes[.size] as? NSNumber,
           size.intValue > 5 * 1024 * 1024 {
            let previous = logURL.deletingLastPathComponent().appendingPathComponent("client.log.1")
            try? FileManager.default.removeItem(at: previous)
            try? FileManager.default.moveItem(at: logURL, to: previous)
        }
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }
        logHandle = try? FileHandle(forWritingTo: logURL)
        logHandle?.seekToEndOfFile()
    }

    private func createMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "AI 语音"

        let menu = NSMenu()
        statusMenuItem = NSMenuItem(title: "正在启动…", action: nil, keyEquivalent: "")
        statusMenuItem.isEnabled = false
        menu.addItem(statusMenuItem)
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "重启客户端", action: #selector(restartClient), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "查看日志", action: #selector(openLog), keyEquivalent: "l"))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "退出", action: #selector(quit), keyEquivalent: "q"))
        for item in menu.items {
            item.target = self
        }
        statusItem.menu = menu
    }

    private func writeLog(_ message: String) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        logHandle?.write(Data("[\(timestamp)] \(message)\n".utf8))
    }

    private func setStatus(_ text: String) {
        statusMenuItem?.title = text
        statusItem?.button?.toolTip = text
    }

    private func startClient() {
        guard !stopping, process?.isRunning != true else { return }
        guard FileManager.default.isExecutableFile(atPath: pythonURL.path) else {
            setStatus("缺少 Python 环境，请重新安装")
            writeLog("找不到 \(pythonURL.path)")
            return
        }

        let token = UUID()
        runToken = token
        let child = Process()
        child.executableURL = pythonURL
        child.arguments = [scriptURL.path]
        child.currentDirectoryURL = scriptURL.deletingLastPathComponent()
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        environment["AI_PASSPORT_APP_BRIDGE"] = "1"
        environment["AI_PASSPORT_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        child.environment = environment
        if let logHandle {
            child.standardOutput = logHandle
            child.standardError = logHandle
        }
        child.terminationHandler = { [weak self] finished in
            DispatchQueue.main.async {
                guard let self else { return }
                guard self.runToken == token else { return }
                self.process = nil
                if self.stopping {
                    self.setStatus("已退出")
                    return
                }
                self.setStatus("客户端已退出，正在重试")
                self.writeLog("客户端退出，状态码 \(finished.terminationStatus)，3 秒后重启")
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                    self.startClient()
                }
            }
        }

        do {
            try child.run()
            process = child
            setStatus("客户端运行中")
            writeLog("已启动客户端，PID \(child.processIdentifier)")
        } catch {
            process = nil
            setStatus("启动失败，正在重试")
            writeLog("启动失败：\(error.localizedDescription)")
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                self.startClient()
            }
        }
    }

    private func stopClient() {
        guard let child = process, child.isRunning else { return }
        runToken = UUID()
        child.terminate()
        let pid = child.processIdentifier
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) {
            if child.isRunning {
                kill(pid, SIGKILL)
            }
        }
        process = nil
    }

    @objc private func restartClient() {
        stopping = true
        stopClient()
        stopping = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.startClient()
        }
    }

    @objc private func openLog() {
        NSWorkspace.shared.open(logURL)
    }

    @objc private func quit() {
        stopping = true
        stopClient()
        NSApplication.shared.terminate(nil)
    }

    private func registerAppBridge() {
        let center = DistributedNotificationCenter.default()
        center.addObserver(
            self,
            selector: #selector(receiveText(_:)),
            name: Notification.Name("com.folo-aipassport.voice.insertText"),
            object: nil,
            suspensionBehavior: .deliverImmediately
        )
        center.addObserver(
            self,
            selector: #selector(receiveEnter(_:)),
            name: Notification.Name("com.folo-aipassport.voice.pressEnter"),
            object: nil,
            suspensionBehavior: .deliverImmediately
        )
    }

    @objc private func receiveText(_ notification: Notification) {
        guard let text = notification.userInfo?["text"] as? String, !text.isEmpty else {
            return
        }
        insertText(text)
    }

    @objc private func receiveEnter(_ notification: Notification) {
        postKey(36)
    }

    private func postKey(_ keyCode: CGKeyCode, flags: CGEventFlags = []) {
        guard CGPreflightPostEventAccess() else {
            writeLog("辅助功能或键盘事件权限未就绪，无法发送键盘事件")
            return
        }
        let source = CGEventSource(stateID: .hidSystemState)
        let down = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: true)
        down?.flags = flags
        down?.post(tap: .cghidEventTap)
        let up = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: false)
        up?.flags = flags
        up?.post(tap: .cghidEventTap)
    }

    private func clipboardSnapshot() -> [[NSPasteboard.PasteboardType: Data]] {
        let pasteboard = NSPasteboard.general
        return (pasteboard.pasteboardItems ?? []).map { item in
            var values: [NSPasteboard.PasteboardType: Data] = [:]
            for valueType in item.types {
                if let data = item.data(forType: valueType) {
                    values[valueType] = data
                }
            }
            return values
        }
    }

    private func restoreClipboard(_ snapshot: [[NSPasteboard.PasteboardType: Data]]) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        let items = snapshot.map { values -> NSPasteboardItem in
            let item = NSPasteboardItem()
            for (valueType, data) in values {
                item.setData(data, forType: valueType)
            }
            return item
        }
        if !items.isEmpty {
            _ = pasteboard.writeObjects(items)
        }
    }

    private func insertText(_ text: String) {
        // WebView/Electron 可能错误地报告 AXSelectedText 写入成功，但界面不会更新。
        // 统一改用系统粘贴，确保 Codex 等应用真正收到文字。
        let snapshot = clipboardSnapshot()
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        guard pasteboard.setString(text, forType: .string) else {
            writeLog("写入系统剪贴板失败")
            return
        }
        postKey(9, flags: .maskCommand)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            self.restoreClipboard(snapshot)
        }
        writeLog("已发送剪贴板粘贴，共 \(text.count) 个字符")
    }

    private func setSelectedText(_ text: String) -> Bool {
        let system = AXUIElementCreateSystemWide()
        var focusedValue: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            system,
            kAXFocusedUIElementAttribute as CFString,
            &focusedValue
        ) == .success, let focusedValue else {
            writeLog("无法获取当前输入框")
            return false
        }
        let result = AXUIElementSetAttributeValue(
            focusedValue as! AXUIElement,
            kAXSelectedTextAttribute as CFString,
            text as CFTypeRef
        )
        if result != .success {
            writeLog("辅助功能直接填字失败，状态码 \(result.rawValue)")
        }
        return result == .success
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.run()
