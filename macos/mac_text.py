"""Paste text at the current focus while restoring the previous clipboard."""
import time


class TextInjectionError(RuntimeError):
    pass


class AppBridgeTextInjector:
    """Ask the menu-bar host app to inject text with its own TCC permission."""

    uses_app_bridge = True

    def __init__(self):
        from Foundation import NSDistributedNotificationCenter
        self.notification_center = NSDistributedNotificationCenter.defaultCenter()

    @property
    def ready(self):
        return True

    def insert(self, text):
        self.notification_center.postNotificationName_object_userInfo_deliverImmediately_(
            'com.folo-aipassport.voice.insertText',
            None,
            {'text': str(text)},
            True,
        )

    def press_enter(self):
        self.notification_center.postNotificationName_object_userInfo_deliverImmediately_(
            'com.folo-aipassport.voice.pressEnter',
            None,
            {},
            True,
        )


class MacTextInjector:
    def __init__(self, keyboard, pasteboard=None, pasteboard_item=None, sleep=None):
        self.keyboard = keyboard
        self._sleep = sleep or time.sleep
        if pasteboard is None or pasteboard_item is None:
            from AppKit import NSPasteboard, NSPasteboardItem
            pasteboard = pasteboard or NSPasteboard.generalPasteboard()
            pasteboard_item = pasteboard_item or NSPasteboardItem
        self.pasteboard = pasteboard
        self.pasteboard_item = pasteboard_item

    @property
    def ready(self):
        return self.keyboard.ready

    def _snapshot(self):
        snapshot = []
        items = self.pasteboard.pasteboardItems() or []
        for item in items:
            data = {}
            for value_type in item.types():
                blob = item.dataForType_(value_type)
                if blob is not None:
                    data[value_type] = bytes(blob)
            snapshot.append(data)
        return snapshot

    def _restore(self, snapshot):
        self.pasteboard.clearContents()
        if not snapshot:
            return
        items = []
        for values in snapshot:
            item = self.pasteboard_item.alloc().init()
            for value_type, blob in values.items():
                item.setData_forType_(blob, value_type)
            items.append(item)
        if items and not self.pasteboard.writeObjects_(items):
            raise TextInjectionError('恢复剪贴板失败；识别文字仍已粘贴')

    def insert(self, text):
        text = str(text)
        if not text:
            return
        if not self.ready:
            raise TextInjectionError('未取得辅助功能权限，无法粘贴文字')

        from AppKit import NSPasteboardTypeString
        from mac_keys import MacKeyInjector

        snapshot = self._snapshot()
        try:
            self.pasteboard.clearContents()
            if not self.pasteboard.setString_forType_(text, NSPasteboardTypeString):
                raise TextInjectionError('无法写入系统剪贴板')
            MacKeyInjector('cmd+v', 'tap', self.keyboard).click()
            self._sleep(0.35)
        finally:
            self._restore(snapshot)
