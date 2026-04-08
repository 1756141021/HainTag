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
    excludes=['onnxruntime'],
    noarchive=False,
    optimize=0,
)
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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='HainTag',
)
