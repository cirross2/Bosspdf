"""
여러 BossPDF 창이 같은 자리에 겹치지 않도록 계단식 배치를 돕는 모듈 (Windows 전용, 그 외 OS는 동작 없음)

각 메인 창은 자기 HWND에 표식과 현재 위치(Qt 논리 좌표)를 윈도우 속성(SetProp)으로 기록합니다.
새 창은 EnumWindows로 이 표식을 가진 창들의 위치를 읽어, 이미 창이 있는 자리면 조금씩 비켜 섭니다.
"""
import sys

PROP_MARK = "BossPDF.MainWindow"
PROP_X = "BossPDF.X"
PROP_Y = "BossPDF.Y"
_OFFSET = 100000  # 음수 좌표(보조 모니터)도 양수 핸들 값으로 저장하기 위한 보정치

CASCADE_STEP = 30
MATCH_TOLERANCE = 12

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
    _user32.SetPropW.restype = wintypes.BOOL
    _user32.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    _user32.GetPropW.restype = wintypes.HANDLE
    _user32.RemovePropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    _user32.RemovePropW.restype = wintypes.HANDLE
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_EnumProc, wintypes.LPARAM]


def publish_position(hwnd: int, x: int, y: int):
    """이 창이 BossPDF 메인 창임과 현재 위치를 기록"""
    if not _IS_WINDOWS or not hwnd:
        return
    try:
        _user32.SetPropW(hwnd, PROP_MARK, 1)
        _user32.SetPropW(hwnd, PROP_X, int(x) + _OFFSET)
        _user32.SetPropW(hwnd, PROP_Y, int(y) + _OFFSET)
    except Exception:
        pass


def unpublish(hwnd: int):
    if not _IS_WINDOWS or not hwnd:
        return
    try:
        for name in (PROP_MARK, PROP_X, PROP_Y):
            _user32.RemovePropW(hwnd, name)
    except Exception:
        pass


def other_window_positions(exclude_hwnd: int = 0):
    """화면에 떠 있는 다른 BossPDF 메인 창들의 위치 목록 [(x, y), ...]"""
    if not _IS_WINDOWS:
        return []
    found = []

    def _cb(hwnd, _lparam):
        try:
            if hwnd == exclude_hwnd or not _user32.GetPropW(hwnd, PROP_MARK):
                return True
            if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
                return True
            x = _user32.GetPropW(hwnd, PROP_X)
            y = _user32.GetPropW(hwnd, PROP_Y)
            if x and y:
                found.append((int(x) - _OFFSET, int(y) - _OFFSET))
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_EnumProc(_cb), 0)
    except Exception:
        return []
    return found


def marked_windows():
    """BossPDF 메인 창 HWND 목록 (최소화 포함, 화면 Z-order 위쪽부터)"""
    if not _IS_WINDOWS:
        return []
    found = []

    def _cb(hwnd, _lparam):
        try:
            if _user32.GetPropW(hwnd, PROP_MARK) and _user32.IsWindowVisible(hwnd):
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        _user32.EnumWindows(_EnumProc(_cb), 0)
    except Exception:
        return []
    return found


def find_free_position(x: int, y: int, occupied, bounds=None):
    """
    (x, y)에 이미 창이 있으면 오른쪽 아래로 CASCADE_STEP씩 비켜 빈 자리를 찾습니다.
    bounds=(left, top, right, bottom, width, height)가 주어지면 창이 화면 밖으로 나가지 않게
    처음 위치 기준으로 되돌아가며 다시 계단을 쌓습니다.
    """
    def taken(px, py):
        return any(abs(px - ox) <= MATCH_TOLERANCE and abs(py - oy) <= MATCH_TOLERANCE
                   for ox, oy in occupied)

    if not occupied or not taken(x, y):
        return x, y

    for k in range(1, 200):
        cx = x + k * CASCADE_STEP
        cy = y + k * CASCADE_STEP
        if bounds:
            # 화면 끝에 닿으면 작업 영역 왼쪽/위쪽으로 돌아와 계속 계단을 쌓음
            left, top, right, bottom, w, h = bounds
            span_x = max(1, right - left - w + 1)
            span_y = max(1, bottom - top - h + 1)
            cx = left + (cx - left) % span_x
            cy = top + (cy - top) % span_y
        if not taken(cx, cy):
            return cx, cy
    return x + CASCADE_STEP, y + CASCADE_STEP
