"""macOS Quartz shortcut backend. No event monitoring or microphone capture."""
import time


class KeyErrorMac(RuntimeError):
    pass


# Apple virtual key codes; these are not Windows scan codes.
CODES = {
    'a': 0, 's': 1, 'd': 2, 'f': 3, 'h': 4, 'g': 5, 'z': 6, 'x': 7, 'c': 8, 'v': 9,
    'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15, 'y': 16, 't': 17,
    '1': 18, '2': 19, '3': 20, '4': 21, '6': 22, '5': 23, '9': 25, '7': 26,
    '8': 28, '0': 29, 'o': 31, 'u': 32, 'i': 34, 'p': 35, 'enter': 36,
    'l': 37, 'j': 38, 'k': 40, 'n': 45, 'm': 46, 'tab': 48, 'space': 49,
    'backspace': 51, 'escape': 53, 'left-command': 55, 'left-shift': 56,
    'left-option': 58, 'left-ctrl': 59, 'right-shift': 60, 'right-option': 61,
    'right-ctrl': 62, 'right-command': 54, 'fn': 63,
    'f1': 122, 'f2': 120, 'f3': 99, 'f4': 118, 'f5': 96, 'f6': 97,
    'f7': 98, 'f8': 100, 'f9': 101, 'f10': 109, 'f11': 103, 'f12': 111,
}
ALIASES = {'ctrl': 'left-ctrl', 'control': 'left-ctrl', 'shift': 'left-shift',
           'alt': 'left-option', 'option': 'left-option', 'left-alt': 'left-option',
           'right-alt': 'right-option', 'cmd': 'left-command', 'command': 'left-command',
           'win': 'left-command', 'left-win': 'left-command', 'right-win': 'right-command',
           'return': 'enter', 'esc': 'escape', 'globe': 'fn'}
MODIFIER_FLAGS = {55: 1 << 20, 54: 1 << 20, 56: 1 << 17, 60: 1 << 17,
                  58: 1 << 19, 61: 1 << 19, 59: 1 << 18, 62: 1 << 18, 63: 1 << 23}


def resolve_key_spec(spec):
    parts = str(spec).lower().split('+')
    keys = []
    for i, part in enumerate(parts):
        name = ALIASES.get(part.strip(), part.strip())
        if name not in CODES:
            raise ValueError(f'不支持的 Mac 键名：{part!r}')
        if i < len(parts) - 1 and CODES[name] not in MODIFIER_FLAGS:
            raise ValueError('组合键的修饰键必须放在普通键之前')
        if CODES[name] in keys:
            raise ValueError('快捷键不能包含重复按键')
        keys.append(CODES[name])
    return keys


class QuartzKeyboard:
    def __init__(self, quartz=None, accessibility=None):
        if quartz is None:
            import Quartz as quartz
        if accessibility is None:
            import ApplicationServices as accessibility
        self.q = quartz
        self.ax = accessibility
        self.modifiers = set()
        self.fault = ''

    def permitted(self):
        try:
            trusted = bool(self.ax.AXIsProcessTrusted())
            preflight = getattr(self.q, 'CGPreflightPostEventAccess', None)
            return trusted and (preflight is None or bool(preflight()))
        except Exception:
            return False

    def request_permission(self):
        requester = getattr(self.ax, 'AXIsProcessTrustedWithOptions', None)
        prompt_key = getattr(self.ax, 'kAXTrustedCheckOptionPrompt', None)
        if requester is None or prompt_key is None:
            return self.ready
        try:
            return bool(requester({prompt_key: True}))
        except Exception:
            return False

    @property
    def ready(self):
        return not self.fault and self.permitted()

    def post(self, code, up=False):
        if not up and not self.ready:
            raise KeyErrorMac(self.fault or '未取得辅助功能权限；授权后请重开转发器')
        try:
            if code in MODIFIER_FLAGS:
                if up:
                    self.modifiers.discard(code)
                else:
                    self.modifiers.add(code)
            event = self.q.CGEventCreateKeyboardEvent(None, code, not up)
            if event is None:
                raise KeyErrorMac('Quartz 未创建键盘事件')
            flags = 0
            for modifier in self.modifiers:
                flags |= MODIFIER_FLAGS[modifier]
            self.q.CGEventSetFlags(event, flags)
            if code in MODIFIER_FLAGS:
                self.q.CGEventSetType(event, self.q.kCGEventFlagsChanged)
            self.q.CGEventPost(self.q.kCGHIDEventTap, event)
        except Exception as error:
            self.fault = str(error)
            raise KeyErrorMac(self.fault) from error


class MacKeyInjector:
    def __init__(self, spec, mode, keyboard):
        if mode not in ('hold', 'tap'):
            raise ValueError('语音快捷键模式必须为 hold 或 tap')
        self._keys = resolve_key_spec(spec)
        self.spec, self.mode, self.keyboard = spec, mode, keyboard
        self._held = self._active = False
        self._pressed = []

    @property
    def ready(self):
        return self.keyboard.ready

    def _release(self):
        pressed, self._pressed = self._pressed, []
        for code in reversed(pressed):
            try:
                self.keyboard.post(code, up=True)
            except KeyErrorMac:
                pass  # Best effort even after permission revocation or a partial press.
        self._held = False

    def _press(self):
        try:
            for code in self._keys:
                # Include the current code in cleanup if posting fails halfway.
                self._pressed.append(code)
                self.keyboard.post(code)
        except Exception:
            self._release()
            raise

    def click(self):
        try:
            self._press()
            time.sleep(.06)
        finally:
            self._release()

    def start(self):
        if self._active:
            return
        try:
            if self.mode == 'hold':
                self._press()
                self._held = True
            else:
                self.click()
            self._active = True
        except Exception:
            self._active = False
            self._release()
            raise

    def stop(self):
        active, self._active = self._active, False
        if self.mode == 'hold':
            self._release()
        elif active and self.ready:
            self.click()
