"""MonitorOff - tray tool that puts all monitors into standby immediately.

Left-click on the tray icon  -> monitors off (after a short delay)
Global hotkey (optional)     -> monitors off
Right-click                  -> menu (monitors off, hotkey, autostart, language, exit)
Mouse/keyboard input         -> monitors back on (handled by Windows itself)

This triggers exactly what the power option "Turn off my screen after x minutes"
does: WM_SYSCOMMAND / SC_MONITORPOWER = 2. The computer itself stays awake.

Run with "--off" to turn the monitors off once and exit.

UI texts live in lang/<code>.json; the Windows display language is used by
default and can be overridden from the tray menu.
Settings (hotkey, language) are stored in HKCU\\Software\\MonitorOff.
Standard library only (ctypes), no third-party runtime dependencies.
"""

import ctypes
import glob
import json
import os
import sys
import winreg
from ctypes import wintypes

__version__ = "1.0.0"

APP_NAME = "MonitorOff"
APP_ICON_FILE = "monitor_off.ico"             # program icon (exe, dialog)
TRAY_ICON_FOR_DARK = "monitor_off_light.ico"  # white glyph for a dark taskbar
TRAY_ICON_FOR_LIGHT = "monitor_off_dark.ico"  # dark glyph for a light taskbar
LANG_DIR = "lang"
FALLBACK_LANGUAGE = "en"
# Delay so that releasing/moving the mouse or keys right after triggering
# does not wake the monitors up again immediately.
DELAY_MS = 1000

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SETTINGS_KEY = rf"Software\{APP_NAME}"
PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

# --- Win32 constants ----------------------------------------------------------
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_SETTINGCHANGE = 0x001A
WM_SETFONT = 0x0030
WM_NCDESTROY = 0x0082
WM_CONTEXTMENU = 0x007B
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_COMMAND = 0x0111
WM_SYSCOMMAND = 0x0112
WM_TIMER = 0x0113
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
KEY_MESSAGES = (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP)

SC_MONITORPOWER = 0xF170
MONITOR_OFF = 2

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10
NIIF_WARNING = 0x02

MF_STRING = 0x0000
MF_CHECKED = 0x0008
MF_POPUP = 0x0010
MF_RADIOCHECK = 0x0200
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_TABSTOP = 0x00010000
WS_EX_DLGMODALFRAME = 0x0001
WS_EX_TOPMOST = 0x0008
WS_EX_CLIENTEDGE = 0x0200
SS_CENTER = 0x0001
SS_CENTERIMAGE = 0x0200
BS_DEFPUSHBUTTON = 0x0001
SW_SHOW = 5
COLOR_BTNFACE = 15
SPI_GETWORKAREA = 0x0030

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
SM_CXICON = 11
SM_CYICON = 12
SM_CXSMICON = 49
SM_CYSMICON = 50
IDI_APPLICATION = 32512
ERROR_ALREADY_EXISTS = 183
LOCALE_NAME_MAX_LENGTH = 85

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_LWIN = 0x5B
VK_RWIN = 0x5C
MODIFIER_VKS = {VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
MAPVK_VK_TO_VSC_EX = 4

# Keys that GetKeyNameText cannot name -> translation keys.
KEY_NAME_IDS = {
    0x13: "key_pause", 0x2C: "key_print",
    0xA6: "key_browser_back", 0xA7: "key_browser_forward", 0xA8: "key_browser_refresh",
    0xA9: "key_browser_stop", 0xAA: "key_browser_search", 0xAB: "key_browser_favorites",
    0xAC: "key_browser_home", 0xAD: "key_volume_mute", 0xAE: "key_volume_down",
    0xAF: "key_volume_up", 0xB0: "key_media_next", 0xB1: "key_media_prev",
    0xB2: "key_media_stop", 0xB3: "key_media_play_pause", 0xB4: "key_launch_mail",
    0xB5: "key_launch_media", 0xB6: "key_launch_app1", 0xB7: "key_launch_app2",
}

TIMER_ID = 1
HOTKEY_ID = 1
CMD_OFF = 1001
CMD_HOTKEY = 1002
CMD_AUTOSTART = 1003
CMD_EXIT = 1004
CMD_LANG_AUTO = 2000
CMD_LANG_FIRST = 2001
IDOK = 1
IDCANCEL = 2
ID_REMOVE = 3

# --- ctypes declarations ------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


def _proto(func, restype, *argtypes):
    func.restype = restype
    func.argtypes = argtypes


_proto(user32.DefWindowProcW, LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_proto(user32.RegisterClassExW, wintypes.ATOM, ctypes.POINTER(WNDCLASSEXW))
_proto(user32.CreateWindowExW, wintypes.HWND, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID)
_proto(user32.DestroyWindow, wintypes.BOOL, wintypes.HWND)
_proto(user32.ShowWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
_proto(user32.SetWindowTextW, wintypes.BOOL, wintypes.HWND, wintypes.LPCWSTR)
_proto(user32.IsChild, wintypes.BOOL, wintypes.HWND, wintypes.HWND)
_proto(user32.SetFocus, wintypes.HWND, wintypes.HWND)
_proto(user32.AdjustWindowRectEx, wintypes.BOOL, ctypes.POINTER(wintypes.RECT), wintypes.DWORD,
       wintypes.BOOL, wintypes.DWORD)
_proto(user32.SystemParametersInfoW, wintypes.BOOL, wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT)
_proto(user32.GetMessageW, wintypes.BOOL, ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
_proto(user32.TranslateMessage, wintypes.BOOL, ctypes.POINTER(wintypes.MSG))
_proto(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wintypes.MSG))
_proto(user32.PostQuitMessage, None, ctypes.c_int)
_proto(user32.SendMessageW, LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_proto(user32.PostMessageW, wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_proto(user32.SetTimer, wintypes.WPARAM, wintypes.HWND, wintypes.WPARAM, wintypes.UINT, wintypes.LPVOID)
_proto(user32.KillTimer, wintypes.BOOL, wintypes.HWND, wintypes.WPARAM)
_proto(user32.RegisterWindowMessageW, wintypes.UINT, wintypes.LPCWSTR)
_proto(user32.RegisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
_proto(user32.UnregisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
_proto(user32.GetKeyState, ctypes.c_short, ctypes.c_int)
_proto(user32.MapVirtualKeyW, wintypes.UINT, wintypes.UINT, wintypes.UINT)
_proto(user32.GetKeyNameTextW, ctypes.c_int, wintypes.LONG, wintypes.LPWSTR, ctypes.c_int)
_proto(user32.CreatePopupMenu, wintypes.HMENU)
_proto(user32.AppendMenuW, wintypes.BOOL, wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR)
_proto(user32.SetMenuDefaultItem, wintypes.BOOL, wintypes.HMENU, wintypes.UINT, wintypes.UINT)
_proto(user32.TrackPopupMenu, ctypes.c_int, wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
       ctypes.c_int, wintypes.HWND, wintypes.LPVOID)
_proto(user32.DestroyMenu, wintypes.BOOL, wintypes.HMENU)
_proto(user32.GetCursorPos, wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
_proto(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
_proto(user32.LoadImageW, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
       ctypes.c_int, ctypes.c_int, wintypes.UINT)
_proto(user32.LoadIconW, wintypes.HICON, wintypes.HINSTANCE, ctypes.c_void_p)
_proto(user32.DestroyIcon, wintypes.BOOL, wintypes.HICON)
_proto(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
_proto(user32.MessageBoxW, ctypes.c_int, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
_proto(shell32.Shell_NotifyIconW, wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
_proto(kernel32.GetModuleHandleW, wintypes.HMODULE, wintypes.LPCWSTR)
_proto(kernel32.CreateMutexW, wintypes.HANDLE, wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_proto(kernel32.GetUserDefaultUILanguage, wintypes.WORD)
_proto(kernel32.LCIDToLocaleName, ctypes.c_int, wintypes.DWORD, wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD)
_proto(gdi32.CreateFontW, wintypes.HFONT, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
       wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
       wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR)
_proto(gdi32.DeleteObject, wintypes.BOOL, wintypes.HGDIOBJ)


# --- Paths --------------------------------------------------------------------
def resource_path(name):
    """Path to a bundled file (PyInstaller extracts to sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def app_dir():
    """Folder of the exe (frozen) or of this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# --- Settings (registry) ------------------------------------------------------
def load_setting(name, default=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def save_setting(name, value):
    reg_type = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as key:
            winreg.SetValueEx(key, name, 0, reg_type, value)
    except OSError:
        pass


def load_hotkey():
    try:
        mods = int(load_setting("HotkeyModifiers", 0)) & 0x0F
        vk = int(load_setting("HotkeyKey", 0)) & 0xFF
        return mods, vk
    except (ValueError, TypeError):
        return 0, 0


def save_hotkey(mods, vk):
    save_setting("HotkeyModifiers", mods)
    save_setting("HotkeyKey", vk)


def autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return f'"{pythonw}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def taskbar_is_light():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY) as key:
            return bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        return False  # Windows 11 default: dark taskbar


# --- Translations -------------------------------------------------------------
def system_ui_locale():
    """Windows display language as locale name, e.g. 'de-DE'."""
    buf = ctypes.create_unicode_buffer(LOCALE_NAME_MAX_LENGTH)
    if kernel32.LCIDToLocaleName(kernel32.GetUserDefaultUILanguage(), buf, LOCALE_NAME_MAX_LENGTH, 0):
        return buf.value
    return FALLBACK_LANGUAGE


class Translator:
    """Loads lang/<code>.json files. Files in a 'lang' folder next to the exe
    override/extend the bundled ones, so languages can be added without a rebuild."""

    def __init__(self):
        self.languages = {}
        for folder in dict.fromkeys([resource_path(LANG_DIR), os.path.join(app_dir(), LANG_DIR)]):
            for path in glob.glob(os.path.join(folder, "*.json")):
                code = os.path.splitext(os.path.basename(path))[0].lower()
                try:
                    with open(path, encoding="utf-8-sig") as f:
                        data = json.load(f)
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict):
                    self.languages[code] = data
        self.system_code = self._match(system_ui_locale())
        self.setting = ""
        self.code = self.system_code
        self.set_language(str(load_setting("Language", "") or ""))

    def _match(self, locale):
        """'de-AT' -> 'de-at' if available, else 'de', else the fallback."""
        locale = locale.lower()
        for candidate in (locale, locale.split("-")[0], FALLBACK_LANGUAGE):
            if candidate in self.languages:
                return candidate
        return next(iter(self.languages), FALLBACK_LANGUAGE)

    def set_language(self, code):
        """code '' = follow the Windows display language."""
        code = code.lower()
        self.setting = code if code in self.languages else ""
        self.code = self.setting or self.system_code

    def name(self, code):
        return self.languages.get(code, {}).get("language_name", code)

    def sorted_codes(self):
        return sorted(self.languages, key=lambda c: self.name(c).lower())

    def __call__(self, key, **kwargs):
        text = (self.languages.get(self.code, {}).get(key)
                or self.languages.get(FALLBACK_LANGUAGE, {}).get(key)
                or key)
        return text.format(**kwargs) if kwargs else text


tr = None  # Translator instance, created in main()


# --- Keyboard helpers ---------------------------------------------------------
def key_name(vk):
    if vk in KEY_NAME_IDS:
        return tr(KEY_NAME_IDS[vk])
    sc = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
    extended = 1 if (sc & 0xFF00) in (0xE000, 0xE100) else 0
    buf = ctypes.create_unicode_buffer(64)
    if sc and user32.GetKeyNameTextW(((sc & 0xFF) << 16) | (extended << 24), buf, 64):
        name = buf.value
        return name.title() if len(name) > 1 and name.isupper() else name
    return tr("key_unknown", code=f"{vk:02X}")


def hotkey_text(mods, vk):
    """vk=None -> incomplete input ("Ctrl + Alt + …")."""
    parts = []
    if mods & MOD_WIN:
        parts.append(tr("mod_win"))
    if mods & MOD_CONTROL:
        parts.append(tr("mod_ctrl"))
    if mods & MOD_ALT:
        parts.append(tr("mod_alt"))
    if mods & MOD_SHIFT:
        parts.append(tr("mod_shift"))
    parts.append("…" if vk is None else key_name(vk))
    return " + ".join(parts)


def current_modifiers():
    def down(vk):
        return user32.GetKeyState(vk) & 0x8000

    mods = 0
    if down(VK_CONTROL):
        mods |= MOD_CONTROL
    if down(VK_MENU):
        mods |= MOD_ALT
    if down(VK_SHIFT):
        mods |= MOD_SHIFT
    if down(VK_LWIN) or down(VK_RWIN):
        mods |= MOD_WIN
    return mods


def allowed_without_modifier(vk):
    # F1-F24, Pause, Print Screen, Scroll Lock, browser/media keys
    return 0x70 <= vk <= 0x87 or vk in (0x13, 0x2C, 0x91) or 0xA6 <= vk <= 0xB7


def system_dpi():
    try:
        return user32.GetDpiForSystem() or 96
    except AttributeError:
        return 96


def load_icon(filename, large=False):
    cx = user32.GetSystemMetrics(SM_CXICON if large else SM_CXSMICON)
    cy = user32.GetSystemMetrics(SM_CYICON if large else SM_CYSMICON)
    path = resource_path(filename)
    if os.path.exists(path):
        hicon = user32.LoadImageW(None, path, IMAGE_ICON, cx, cy, LR_LOADFROMFILE)
        if hicon:
            return hicon
    return None


# --- Hotkey dialog ------------------------------------------------------------
class HotkeyDialog:
    CLASS_NAME = f"{APP_NAME}HotkeyDialog"

    def __init__(self, app):
        self.app = app
        self.hwnd = None        # only set once CreateWindowExW returns
        self.candidate = None   # (mods, vk) of the last complete combination
        self.typing = False     # modifiers held, main key still missing
        self.applied = False

        dpi = system_dpi()

        def s(v):
            return v * dpi // 96

        self.font = gdi32.CreateFontW(-(9 * dpi // 72), 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self.font_big = gdi32.CreateFontW(-(13 * dpi // 72), 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")

        style = WS_POPUP | WS_CAPTION | WS_SYSMENU
        exstyle = WS_EX_DLGMODALFRAME | WS_EX_TOPMOST
        rect = wintypes.RECT(0, 0, s(380), s(172))
        user32.AdjustWindowRectEx(ctypes.byref(rect), style, False, exstyle)
        width, height = rect.right - rect.left, rect.bottom - rect.top
        work = wintypes.RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0)
        x = work.left + (work.right - work.left - width) // 2
        y = work.top + (work.bottom - work.top - height) // 2

        app.dialog = self
        self.hwnd = user32.CreateWindowExW(exstyle, self.CLASS_NAME, tr("dialog_title", app=APP_NAME),
                                           style, x, y, width, height, None, None, app.hinst, None)

        def child(cls, text, cstyle, x, y, w, h, cid=0, ex=0, font=None):
            hw = user32.CreateWindowExW(ex, cls, text, WS_CHILD | WS_VISIBLE | cstyle,
                                        s(x), s(y), s(w), s(h), self.hwnd, cid, app.hinst, None)
            user32.SendMessageW(hw, WM_SETFONT, font or self.font, 1)
            return hw

        child("STATIC", tr("dialog_prompt"), 0, 16, 14, 348, 20)
        self.display = child("STATIC", "", SS_CENTER | SS_CENTERIMAGE, 16, 38, 348, 40,
                             ex=WS_EX_CLIENTEDGE, font=self.font_big)
        self.status = child("STATIC", tr("dialog_hint"), 0, 16, 86, 348, 36)
        child("BUTTON", tr("button_remove"), WS_TABSTOP, 16, 128, 120, 30, ID_REMOVE)
        child("BUTTON", tr("button_apply"), WS_TABSTOP | BS_DEFPUSHBUTTON, 166, 128, 96, 30, IDOK)
        child("BUTTON", tr("button_cancel"), WS_TABSTOP, 268, 128, 96, 30, IDCANCEL)
        self.show_current()

        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        user32.SetFocus(self.hwnd)

    def show_current(self):
        if self.candidate:
            text = hotkey_text(*self.candidate)
        elif self.app.hotkey[1]:
            text = hotkey_text(*self.app.hotkey)
        else:
            text = tr("dialog_no_hotkey")
        user32.SetWindowTextW(self.display, text)

    def set_status(self, text):
        user32.SetWindowTextW(self.status, text)

    def handle_key(self, msg):
        """Called from the message loop before keys reach buttons etc.
        Returns True if the message was consumed."""
        if msg.message not in KEY_MESSAGES:
            return False
        if msg.hWnd != self.hwnd and not user32.IsChild(self.hwnd, msg.hWnd):
            return False

        vk = msg.wParam & 0xFF
        is_down = msg.message in (WM_KEYDOWN, WM_SYSKEYDOWN)
        mods = current_modifiers()

        if vk in MODIFIER_VKS:
            if is_down:
                self.typing = True
                user32.SetWindowTextW(self.display, hotkey_text(mods, None))
            elif self.typing:
                if mods:
                    user32.SetWindowTextW(self.display, hotkey_text(mods, None))
                else:
                    self.typing = False
                    self.show_current()
            return True

        if not is_down:
            return True
        self.typing = False

        if not mods and vk == VK_RETURN:
            self.apply()
        elif not mods and vk == VK_ESCAPE:
            self.close()
        elif not mods and not allowed_without_modifier(vk):
            self.show_current()
            self.set_status(tr("dialog_needs_modifier", key=key_name(vk)))
        else:
            self.candidate = (mods, vk)
            self.show_current()
            self.set_status(tr("dialog_hint"))
        return True

    def apply(self):
        if self.candidate is None or self.candidate == self.app.hotkey:
            self.close()
            return
        if self.app.set_hotkey(*self.candidate):
            self.applied = True
            self.close()
        else:
            self.set_status(tr("dialog_in_use", hotkey=hotkey_text(*self.candidate)))

    def remove(self):
        self.app.set_hotkey(0, 0)
        self.applied = True
        self.close()

    def close(self):
        user32.DestroyWindow(self.hwnd)

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_COMMAND:
            cid = wparam & 0xFFFF
            if cid == IDOK:
                self.apply()
            elif cid == IDCANCEL:
                self.close()
            elif cid == ID_REMOVE:
                self.remove()
            return 0
        if msg == WM_CLOSE:
            self.close()
            return 0
        if msg == WM_NCDESTROY:
            gdi32.DeleteObject(self.font)
            gdi32.DeleteObject(self.font_big)
            self.app.dialog = None
            if not self.applied:
                self.app.register_hotkey()  # re-enable the previous hotkey
            self.app.update_icon()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


# --- Tray application ---------------------------------------------------------
class TrayApp:
    def __init__(self, tray=True):
        self.tray = tray
        self.hinst = kernel32.GetModuleHandleW(None)
        self.dialog = None
        self.hotkey = (0, 0)
        self.hotkey_registered = False
        self.menu_languages = []
        self.msg_taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

        # Keep references to the callbacks, otherwise they get garbage-collected.
        self.wndproc = WNDPROC(self._wnd_proc)
        self.dlg_wndproc = WNDPROC(self._dlg_wnd_proc)

        self.hicon = None
        self.app_icon = self.app_icon_small = None
        if tray:
            self.app_icon = load_icon(APP_ICON_FILE, large=True)
            self.app_icon_small = load_icon(APP_ICON_FILE)
            self.hicon = self._load_tray_icon()
        main_class = self._register_class(f"{APP_NAME}Window", self.wndproc)
        if tray:
            self._register_class(HotkeyDialog.CLASS_NAME, self.dlg_wndproc,
                                 background=COLOR_BTNFACE + 1)

        # Hidden top-level window (not message-only, so that DefWindowProc
        # handles SC_MONITORPOWER and broadcasts like TaskbarCreated arrive).
        self.hwnd = user32.CreateWindowExW(0, main_class, APP_NAME, 0, 0, 0, 0, 0,
                                           None, None, self.hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        if tray:
            self.hotkey = load_hotkey()
            ok = self.register_hotkey()
            self._add_icon()
            if not ok:
                self.balloon(tr("balloon_hotkey_title"),
                             tr("balloon_hotkey_text", hotkey=hotkey_text(*self.hotkey)))

    def _register_class(self, name, wndproc, background=0):
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = wndproc
        wc.hInstance = self.hinst
        wc.hIcon = self.app_icon
        wc.hIconSm = self.app_icon_small
        wc.hbrBackground = background
        wc.lpszClassName = name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        return name

    # Tray icon -----------------------------------------------------------------
    def _load_tray_icon(self):
        filename = TRAY_ICON_FOR_LIGHT if taskbar_is_light() else TRAY_ICON_FOR_DARK
        return load_icon(filename) or user32.LoadIconW(None, IDI_APPLICATION)

    def refresh_tray_icon(self):
        """After switching between light and dark Windows mode."""
        old = self.hicon
        self.hicon = self._load_tray_icon()
        self.update_icon()
        if old:
            user32.DestroyIcon(old)

    def _hotkey_label(self):
        if not self.hotkey[1]:
            return None
        label = hotkey_text(*self.hotkey)
        if not self.hotkey_registered and not self.dialog:
            label = tr("menu_hotkey_in_use", hotkey=label)
        return label

    def _nid(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.hicon
        label = self._hotkey_label()
        tip = tr("tooltip_hotkey", hotkey=label) if label else tr("tooltip")
        nid.szTip = tip[:127]
        return nid

    def _add_icon(self):
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid()))

    def update_icon(self):
        if self.tray:
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid()))

    def _remove_icon(self):
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))

    def balloon(self, title, text):
        nid = self._nid()
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = text[:255]
        nid.dwInfoFlags = NIIF_WARNING
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # Hotkey --------------------------------------------------------------------
    def register_hotkey(self):
        if self.hotkey_registered or not self.hotkey[1]:
            return True
        mods, vk = self.hotkey
        self.hotkey_registered = bool(user32.RegisterHotKey(self.hwnd, HOTKEY_ID, mods | MOD_NOREPEAT, vk))
        return self.hotkey_registered

    def unregister_hotkey(self):
        if self.hotkey_registered:
            user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)
            self.hotkey_registered = False

    def set_hotkey(self, mods, vk):
        """Register and save a new hotkey. Returns False if it is already taken."""
        self.unregister_hotkey()
        if vk and not user32.RegisterHotKey(self.hwnd, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            return False
        self.hotkey = (mods, vk)
        self.hotkey_registered = bool(vk)
        save_hotkey(mods, vk)
        self.update_icon()
        return True

    def open_hotkey_dialog(self):
        if self.dialog:
            user32.SetForegroundWindow(self.dialog.hwnd)
            return
        # Disable while recording, so pressing the current combination shows
        # up in the dialog instead of turning the monitors off.
        self.unregister_hotkey()
        HotkeyDialog(self)

    # Language ------------------------------------------------------------------
    def set_language(self, code):
        tr.set_language(code)
        save_setting("Language", tr.setting)
        self.update_icon()

    # Actions -------------------------------------------------------------------
    def schedule_off(self, delay_ms=DELAY_MS):
        # Triggering again during the delay just restarts the timer.
        user32.SetTimer(self.hwnd, TIMER_ID, delay_ms, None)

    def monitors_off(self):
        # DefWindowProc forwards SC_MONITORPOWER to Windows - exactly what the
        # power plan timeout "Turn off my screen" triggers.
        user32.SendMessageW(self.hwnd, WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF)

    def _build_language_menu(self):
        menu = user32.CreatePopupMenu()
        radio = MF_STRING | MF_RADIOCHECK
        auto_label = tr("menu_language_auto", language=tr.name(tr.system_code))
        user32.AppendMenuW(menu, radio | (0 if tr.setting else MF_CHECKED), CMD_LANG_AUTO, auto_label)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        self.menu_languages = tr.sorted_codes()
        for i, code in enumerate(self.menu_languages):
            checked = MF_CHECKED if tr.setting == code else 0
            user32.AppendMenuW(menu, radio | checked, CMD_LANG_FIRST + i, tr.name(code))
        return menu

    def show_menu(self):
        label = self._hotkey_label() or tr("menu_hotkey_none")
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, CMD_OFF, tr("menu_turn_off"))
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_HOTKEY, f"{tr('menu_set_hotkey')}\t{label}")
        flags = MF_STRING | (MF_CHECKED if autostart_enabled() else 0)
        user32.AppendMenuW(menu, flags, CMD_AUTOSTART, tr("menu_autostart"))
        user32.AppendMenuW(menu, MF_POPUP, self._build_language_menu(), tr("menu_language"))
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_EXIT, tr("menu_exit"))
        user32.SetMenuDefaultItem(menu, CMD_OFF, 0)

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        # Required so the menu closes when the user clicks elsewhere.
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)  # also destroys the language submenu

        if cmd == CMD_OFF:
            self.schedule_off()
        elif cmd == CMD_HOTKEY:
            self.open_hotkey_dialog()
        elif cmd == CMD_AUTOSTART:
            try:
                set_autostart(not autostart_enabled())
            except OSError as exc:
                user32.MessageBoxW(self.hwnd, tr("autostart_error", error=exc), APP_NAME, 0x10)
        elif cmd == CMD_LANG_AUTO:
            self.set_language("")
        elif CMD_LANG_FIRST <= cmd < CMD_LANG_FIRST + len(self.menu_languages):
            self.set_language(self.menu_languages[cmd - CMD_LANG_FIRST])
        elif cmd == CMD_EXIT:
            user32.DestroyWindow(self.hwnd)

    # Window procedures ---------------------------------------------------------
    def _dlg_wnd_proc(self, hwnd, msg, wparam, lparam):
        # During CreateWindowExW dialog.hwnd is still None -> DefWindowProc.
        if self.dialog and self.dialog.hwnd == hwnd:
            return self.dialog.wnd_proc(hwnd, msg, wparam, lparam)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event == WM_LBUTTONUP:
                self.schedule_off()
            elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self.show_menu()
            return 0
        if msg == WM_HOTKEY and wparam == HOTKEY_ID:
            self.schedule_off()
            return 0
        if msg == WM_TIMER and wparam == TIMER_ID:
            user32.KillTimer(hwnd, TIMER_ID)
            self.monitors_off()
            if not self.tray:  # --off mode: exit afterwards
                user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_SETTINGCHANGE and self.tray and lparam:
            if ctypes.wstring_at(lparam) == "ImmersiveColorSet":
                self.refresh_tray_icon()
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        if msg == self.msg_taskbar_created and self.tray:
            self._add_icon()  # Explorer was restarted
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            if self.dialog:
                self.dialog.applied = True  # do not re-register anything on exit
                self.dialog.close()
            self.unregister_hotkey()
            if self.tray:
                self._remove_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if self.dialog and self.dialog.handle_key(msg):
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for icon in (self.hicon, self.app_icon, self.app_icon_small):
            if icon:
                user32.DestroyIcon(icon)


def main():
    global tr
    try:  # crisp icons/menus at scaling > 100 %
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass

    tr = Translator()

    if "--off" in sys.argv[1:]:
        app = TrayApp(tray=False)
        app.schedule_off(500)
        app.run()
        return

    # Allow only a single instance.
    mutex = kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}_SingleInstance")
    if mutex and ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return

    TrayApp().run()


if __name__ == "__main__":
    main()
