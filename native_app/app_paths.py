"""Single source of truth for the per-platform application data directory.

Several subsystems (settings storage, the onnxruntime venv, the local
tagger's model search) need the same user-writable HainTag directory. They
used to each inline the platform branch; this centralizes it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir(app_name: str = "HainTag") -> Path:
    """Return the user-writable data dir for ``app_name`` on this platform.

    macOS:        ~/Library/Application Support/<app_name>
    Windows/else: %APPDATA%/<app_name>  (falls back to ~/AppData/Roaming)
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / app_name
