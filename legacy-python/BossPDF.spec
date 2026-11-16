# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

winrt_datas, winrt_binaries, winrt_hiddenimports = collect_all('winrt')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=winrt_binaries,
    datas=[('resources', 'resources')] + winrt_datas,
    hiddenimports=winrt_hiddenimports + [
        'PySide6.QtSvg',
        'winrt.windows.media.ocr',
        'winrt.windows.globalization',
        'winrt.windows.storage.streams',
        'winrt.windows.graphics.imaging',
        'winrt.windows.foundation',
        'winrt.windows.foundation.collections',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 코드에서 쓰지 않지만 의존성 탐색으로 딸려 오는 대형 패키지 제외 (용량·시작 속도)
    excludes=[
        'pandas', 'numpy', 'lxml', 'pytz', 'tkinter', 'matplotlib', 'scipy', 'IPython',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtNetwork', 'PySide6.QtOpenGL', 'PySide6.QtPdf',
    ],
    noarchive=False,
    optimize=0,
)

# 위젯 앱에 필요 없는 Qt 바이너리·플러그인·번역 파일 제거
_QT_DROP = (
    'opengl32sw.dll', 'qt6qml', 'qt6quick', 'qt6virtualkeyboard', 'qt6pdf', 'qt6network', 'qt6opengl',
    'qtvirtualkeyboardplugin', 'qpdf.dll', 'qtuiotouchplugin',
)
def _keep(entry):
    name = entry[0].replace('\\', '/').lower()
    if '/translations/' in name and name.endswith('.qm'):
        return False
    if '/plugins/tls/' in name or '/plugins/networkinformation/' in name:
        return False
    return not any(token in name.rsplit('/', 1)[-1] for token in _QT_DROP)
a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BossPDF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources\\app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BossPDF',
)
