"""
BossPDF 단일 실행(Single Instance) 지원 - Windows 전용, 그 외 OS는 항상 새로 실행

이미 BossPDF 창이 떠 있으면, 새로 실행된 프로세스는 PySide6를 불러오기 전에
열 파일 경로를 WM_COPYDATA로 기존 프로세스에 넘기고 바로 종료합니다.
기존 프로세스는 같은 프로세스 안에 새 창을 띄우므로 두 번째 문서부터는 거의 즉시 열립니다.

이 모듈은 시작 속도를 위해 ctypes만 사용합니다 (Qt는 handle_native_message 안에서만 사용).
"""
import os
import sys

from core import window_cascade

MAGIC = 0x42504446  # 'BPDF'
WM_COPYDATA = 0x004A
SMTO_ABORTIFHUNG = 0x0002
ASFW_ANY = -1

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class COPYDATASTRUCT(ctypes.Structure):
        _fields_ = [
            ("dwData", ctypes.c_size_t),
            ("cbData", wintypes.DWORD),
            ("lpData", ctypes.c_void_p),
        ]

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
    ]
    _user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    _user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]


def _encode_request(paths) -> bytes:
    clean = [os.path.abspath(p) for p in paths if p]
    return ("OPEN\n" + "\n".join(clean)).encode("utf-8")


def _decode_request(data: bytes):
    text = data.decode("utf-8", errors="replace")
    if not text.startswith("OPEN"):
        return None
    return [line for line in text.split("\n")[1:] if line.strip()]


def forward_to_running_instance(paths, timeout_ms: int = 3000) -> bool:
    """
    실행 중인 BossPDF 창에 열기 요청을 전달합니다.
    받는 쪽이 처리했다고 응답(1)하면 True. 창이 없거나 이전 버전이라 처리하지 못하면 False.
    """
    if not _IS_WINDOWS:
        return False
    try:
        hwnds = window_cascade.marked_windows()
    except Exception:
        return False
    if not hwnds:
        return False

    payload = _encode_request(paths)
    buf = ctypes.create_string_buffer(payload, len(payload))
    cds = COPYDATASTRUCT(MAGIC, len(payload), ctypes.cast(buf, ctypes.c_void_p))
    try:
        _user32.AllowSetForegroundWindow(ASFW_ANY & 0xFFFFFFFF)
    except Exception:
        pass

    for hwnd in hwnds:  # Z-order 위쪽(최근에 쓴) 창부터 시도
        result = ctypes.c_size_t(0)
        ok = _user32.SendMessageTimeoutW(
            hwnd, WM_COPYDATA, 0, ctypes.addressof(cds),
            SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result),
        )
        if ok and result.value == 1:
            return True
    return False


def handle_native_message(event_type, message, on_request) -> bool:
    """
    MainWindow.nativeEvent에서 호출. BossPDF 열기 요청이면 on_request(paths)를
    다음 이벤트 루프에서 실행하도록 예약하고 True를 반환합니다.
    """
    if not _IS_WINDOWS:
        return False
    try:
        et = bytes(event_type.data()) if hasattr(event_type, "data") else event_type
        if isinstance(et, str):
            et = et.encode()
        if et != b"windows_generic_MSG":
            return False
        msg = wintypes.MSG.from_address(int(message))
        if msg.message != WM_COPYDATA or not msg.lParam:
            return False
        cds = COPYDATASTRUCT.from_address(msg.lParam)
        if cds.dwData != MAGIC or not cds.lpData:
            return False
        paths = _decode_request(ctypes.string_at(cds.lpData, cds.cbData))
        if paths is None:
            return False
    except Exception:
        return False

    # SendMessage 처리 중에는 보내는 쪽이 기다리므로, 실제 창 열기는 이벤트 루프로 미룸
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, lambda: on_request(paths))
    return True
