# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS .app bundle.

Mirrors AITagGenerator.spec (Windows) but:
  - uses POSIX data paths,
  - drops the Windows-only EXE icon / version resource and the
    api-ms-win-* DLL stripping,
  - adds a BUNDLE step producing HainTag.app with an .icns icon.

Build:  pyinstaller HainTag-mac.spec --noconfirm
Output: dist/HainTag.app
"""
import os

# Single source of truth for the version string (native_app/_version.py).
_version_ns = {}
with open('native_app/_version.py', encoding='utf-8') as _vf:
    exec(_vf.read(), _version_ns)
APP_VERSION = _version_ns['__version__']

# Data files. danbooru_all_2.csv is a large gitignored asset kept out of the
# repo; include it only when present so this spec works for both a full
# release build and a CSV-less verification build.
datas = [
    ('native_app/resources', 'native_app/resources'),
    ('CHANGELOG.md', '.'),
    ('native_app/tagger_subprocess.py', 'native_app'),
]
if os.path.exists('danbooru_all_2.csv'):
    datas.append(('danbooru_all_2.csv', '.'))
else:
    print('WARNING [HainTag-mac.spec]: danbooru_all_2.csv not found — '
          'tag dictionary will be absent from this build.')


a = Analysis(
    ['native_app/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'onnxruntime',
        # huggingface_hub in tagger.py is only used to download the model;
        # the ML backends below are never needed — inference runs through the
        # onnxruntime subprocess.
        'torch', 'torchvision', 'torchaudio', 'torch.distributed', 'torch.testing',
        'transformers', 'tokenizers', 'safetensors', 'accelerate',
        'scipy', 'scipy.signal', 'scipy.sparse', 'scipy.linalg',
        'matplotlib', 'matplotlib.pyplot', 'matplotlib.backends',
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

app = BUNDLE(
    coll,
    name='HainTag.app',
    icon='native_app/resources/icon.icns',
    bundle_identifier='com.hein.haintag',
    version=APP_VERSION,
    info_plist={
        'CFBundleName': 'HainTag',
        'CFBundleDisplayName': 'HainTag',
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_VERSION,
        'NSHighResolutionCapable': True,
        # Follow the system light/dark appearance instead of forcing Aqua.
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '11.0',
    },
)
