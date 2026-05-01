# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['native_app\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('native_app\\resources', 'native_app\\resources'), ('danbooru_all_2.csv', '.'), ('CHANGELOG.md', '.'), ('native_app\\tagger_subprocess.py', 'native_app')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'onnxruntime',
        'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtQuickWidgets', 'PyQt6.QtWebEngine',
        'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
        'PyQt6.QtCharts', 'PyQt6.Qt3DCore', 'PyQt6.Qt3DRender', 'PyQt6.Qt3DInput',
        'PyQt6.QtPositioning', 'PyQt6.QtRemoteObjects', 'PyQt6.QtSensors',
        'PyQt6.QtSerialPort', 'PyQt6.QtNfc', 'PyQt6.QtBluetooth',
        'PyQt6.QtTextToSpeech', 'PyQt6.QtSpatialAudio',
        'tkinter', 'unittest', 'pydoc_data', 'test', 'lib2to3',
    ],
    noarchive=False,
    optimize=0,
)

# Strip redundant Windows UCRT API-set forwarder DLLs (provided by Windows 10+).
# They are ~50 stubs that just clutter dist/_internal/ and add no startup value
# on modern Windows.
a.binaries = [b for b in a.binaries if not b[0].lower().startswith('api-ms-win-')]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HainTag',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    icon='native_app/resources/icon.ico',
    version='version_info.py',
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='HainTag',
)
