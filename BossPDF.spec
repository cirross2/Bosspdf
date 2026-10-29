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
    excludes=[],
    noarchive=False,
    optimize=0,
)
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
