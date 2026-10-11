"""Give the app window (Edge/Chrome in --app mode) its own identity on the Windows taskbar.

Without this, Windows treats the window as part of Edge: the taskbar shows Edge's icon and "Pin to taskbar"
pins Edge. Windows lets a window carry its own AppUserModelID plus relaunch properties (the icon, the name and
the command a pinned button runs) — Chrome does the same for its app windows. We set them on the window with
the shell's property store (plain ctypes, no extra packages):
- System.AppUserModel.ID                         → "EnglishPractice.App" (own taskbar group)
- System.AppUserModel.RelaunchCommand            → Baslat.bat (a pinned button starts the app)
- System.AppUserModel.RelaunchDisplayNameResource → "English Practice"
- System.AppUserModel.RelaunchIconResource       → app/frontend/icon.ico (the app's logo)
"""

import ctypes
import logging
import time
from ctypes import wintypes

log = logging.getLogger("launcher")

APP_ID = "EnglishPractice.App"
WINDOW_TITLE = "English Practice"  # the page's <title>; an app window shows exactly this (no " - Microsoft Edge")
WINDOW_CLASS = "Chrome_WidgetWin_1"


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text: str):
        super().__init__()
        ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(self))


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):  # only the VT_LPWSTR case
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("pwszVal", ctypes.c_wchar_p), ("pad", ctypes.c_void_p)]


VT_LPWSTR = 31
FMTID_APPUSERMODEL = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
PID_RELAUNCH_COMMAND, PID_RELAUNCH_ICON, PID_RELAUNCH_NAME, PID_ID = 2, 3, 4, 5
IID_IPROPERTYSTORE = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"


def _set_properties(hwnd: int, values: list[tuple[int, str]]) -> None:
    store = ctypes.c_void_p()
    ctypes.windll.shell32.SHGetPropertyStoreForWindow(wintypes.HWND(hwnd), ctypes.byref(GUID(IID_IPROPERTYSTORE)),
                                                      ctypes.byref(store))
    if not store:
        raise OSError("no property store for the window")
    vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))
    set_value = proto(vtbl[6])                                             # IPropertyStore::SetValue
    commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtbl[7])  # IPropertyStore::Commit
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    try:
        for pid, text in values:  # the relaunch properties first, the ID last (Windows reads them with the ID)
            key = PROPERTYKEY(GUID(FMTID_APPUSERMODEL), pid)
            value = PROPVARIANT(VT_LPWSTR, 0, 0, 0, text, None)
            set_value(store, ctypes.byref(key), ctypes.byref(value))
        commit(store)
    finally:
        release(store)


def _app_windows() -> list[int]:
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            cls = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, title, 256)
            user32.GetClassNameW(hwnd, cls, 64)
            if title.value == WINDOW_TITLE and cls.value == WINDOW_CLASS:
                found.append(hwnd)
        return True

    user32.EnumWindows(visit, 0)
    return found


def claim_app_windows(relaunch_command: str, icon_path: str, timeout: float = 30) -> int:
    """Wait for the app window(s) and give them the app's identity. Returns how many were set."""
    ctypes.windll.ole32.CoInitialize(None)
    deadline = time.monotonic() + timeout
    done: set[int] = set()
    while time.monotonic() < deadline:
        for hwnd in _app_windows():
            if hwnd in done:
                continue
            try:
                _set_properties(hwnd, [(PID_RELAUNCH_COMMAND, relaunch_command),
                                       (PID_RELAUNCH_NAME, "English Practice"),
                                       (PID_RELAUNCH_ICON, icon_path),
                                       (PID_ID, APP_ID)])
                done.add(hwnd)
            except OSError as e:
                log.warning("Pencere kimliği ayarlanamadı: %s", e)
        if done:
            return len(done)
        time.sleep(0.3)
    return 0
