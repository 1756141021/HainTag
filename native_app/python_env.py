"""Managed Python environment for the onnxruntime subprocess fallback.

When the host Python can't load onnxruntime, this module provisions a
self-contained Python with onnxruntime, numpy, and Pillow:

- Windows: downloads the Python 3.12 embeddable package and bootstraps pip.
- macOS: there is no embeddable distribution, so we create a venv from a
  host python3 (Homebrew or system) and pip-install into it.
"""
from __future__ import annotations

import locale
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from PyQt6.QtCore import QThread, pyqtSignal

# ── Constants ──

_IS_MAC = sys.platform == "darwin"

PYTHON_VERSION = "3.12.8"
PYTHON_EMBED_ZIP = f"python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{PYTHON_EMBED_ZIP}"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
REQUIRED_PACKAGES = ["onnxruntime", "numpy", "Pillow"]

# pip mirror for Chinese locale
_TSINGHUA_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _env_dir() -> str:
    """Return the managed Python environment directory path."""
    if _IS_MAC:
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("APPDATA", "")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
    return os.path.join(base, "HainTag", "python_env")


def _python_exe_in(env_dir: str) -> str:
    """Return the interpreter path for the env layout of this platform."""
    if _IS_MAC:
        return os.path.join(env_dir, "bin", "python3")
    return os.path.join(env_dir, "python.exe")


def _find_host_python() -> str | None:
    """Locate a host python3 suitable for `python3 -m venv` on macOS."""
    for name in ("python3.12", "python3.11", "python3"):
        found = shutil.which(name)
        if found:
            return found
    for path in (
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ):
        if os.path.isfile(path):
            return path
    return None


def get_embedded_python_path() -> str | None:
    """Return path to the managed interpreter if it exists, else None."""
    python_exe = _python_exe_in(_env_dir())
    return python_exe if os.path.isfile(python_exe) else None


def is_env_usable(python_path: str) -> bool:
    """Test whether the given Python can import onnxruntime."""
    try:
        result = subprocess.run(
            [python_path, "-c", "import onnxruntime"],
            capture_output=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def _should_use_mirror() -> bool:
    """Detect if we should use a Chinese pip mirror based on system locale."""
    try:
        lang = locale.getdefaultlocale()[0] or ""
        return lang.startswith("zh")
    except Exception:
        return False


def _pip_index_args() -> list[str]:
    """Return pip index URL args if mirror should be used."""
    if _should_use_mirror():
        return ["-i", _TSINGHUA_MIRROR]
    return []


def _download_file(url: str, dest: str,
                   progress_cb=None, label: str = "") -> None:
    """Download a file with optional progress callback.

    Args:
        progress_cb: callable(message: str, percent: int) or None
    """
    req = Request(url, headers={"User-Agent": "HainTag/1.0"})
    resp = urlopen(req, timeout=60)
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 8192

    with open(dest, "wb") as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb and total > 0:
                pct = int(downloaded * 100 / total)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                progress_cb(
                    f"{label} ({mb_done:.1f}/{mb_total:.1f} MB)", pct
                )


class PythonEnvSetupWorker(QThread):
    """Background worker that downloads and sets up an embedded Python env."""

    progress = pyqtSignal(str, int)   # message, percent (0-100)
    finished = pyqtSignal(str)        # interpreter path
    error = pyqtSignal(str)           # error message

    def run(self):
        try:
            if _IS_MAC:
                self._setup_mac()
            else:
                self._setup()
        except Exception as exc:
            self.error.emit(str(exc))

    def _setup(self):
        env_dir = _env_dir()
        os.makedirs(env_dir, exist_ok=True)
        python_exe = os.path.join(env_dir, "python.exe")

        # ── Step 1: Download Python embeddable zip ──
        zip_path = os.path.join(env_dir, PYTHON_EMBED_ZIP)
        if not os.path.isfile(python_exe):
            self.progress.emit("正在下载 Python 3.12...", 5)

            def _dl_progress(msg, pct):
                # Map 5-40%
                self.progress.emit(msg, 5 + int(pct * 0.35))

            _download_file(PYTHON_EMBED_URL, zip_path,
                           progress_cb=_dl_progress,
                           label="下载 Python")

            if self.isInterruptionRequested():
                return

            # ── Step 2: Extract ──
            self.progress.emit("正在解压 Python...", 42)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(env_dir)

            # Clean up zip
            try:
                os.remove(zip_path)
            except OSError:
                pass

            if not os.path.isfile(python_exe):
                self.error.emit("解压后未找到 python.exe")
                return

            # ── Step 3: Patch ._pth file to enable site-packages ──
            self.progress.emit("正在配置 Python...", 48)
            self._patch_pth(env_dir)
        else:
            self.progress.emit("Python 已存在，检查依赖...", 50)

        if self.isInterruptionRequested():
            return

        # ── Step 4: Install pip ──
        pip_exe = os.path.join(env_dir, "Scripts", "pip.exe")
        if not os.path.isfile(pip_exe):
            get_pip_path = os.path.join(env_dir, "get-pip.py")
            self.progress.emit("正在下载 pip 安装器...", 52)

            def _pip_dl_progress(msg, pct):
                self.progress.emit(msg, 52 + int(pct * 0.08))

            _download_file(GET_PIP_URL, get_pip_path,
                           progress_cb=_pip_dl_progress,
                           label="下载 pip")

            self.progress.emit("正在安装 pip...", 62)
            result = subprocess.run(
                [python_exe, get_pip_path, "--no-warn-script-location"],
                capture_output=True, text=True, timeout=120,
                creationflags=_CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                self.error.emit(f"pip 安装失败: {result.stderr.strip()}")
                return

            # Clean up get-pip.py
            try:
                os.remove(get_pip_path)
            except OSError:
                pass

        if self.isInterruptionRequested():
            return

        # ── Step 5: Install packages ──
        self.progress.emit("正在安装 onnxruntime, numpy, Pillow...", 68)
        cmd = [
            python_exe, "-m", "pip", "install",
            "--no-warn-script-location",
            *REQUIRED_PACKAGES,
            *_pip_index_args(),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            self.error.emit(f"依赖安装失败: {result.stderr.strip()}")
            return

        if self.isInterruptionRequested():
            return

        # ── Step 6: Validate ──
        self.progress.emit("正在验证环境...", 95)
        if not is_env_usable(python_exe):
            self.error.emit("环境验证失败：onnxruntime 无法在下载的 Python 中加载")
            return

        self.progress.emit("✓ 环境配置完成", 100)
        self.finished.emit(python_exe)

    def _setup_mac(self):
        """Provision a venv from a host python3 and install onnxruntime into it.

        macOS has no embeddable Python distribution, so instead of downloading
        an interpreter we build a venv from whatever python3 is on the system.
        """
        env_dir = _env_dir()
        os.makedirs(os.path.dirname(env_dir), exist_ok=True)
        python_exe = _python_exe_in(env_dir)

        # ── Step 1: Create the venv (skip if interpreter already present) ──
        if not os.path.isfile(python_exe):
            host = _find_host_python()
            if host is None:
                self.error.emit(
                    "未找到系统 python3。请先安装 Python，例如：\n"
                    "  brew install python@3.12\n"
                    "或从 python.org 安装后重试。"
                )
                return

            self.progress.emit("正在创建 Python 虚拟环境...", 10)
            result = subprocess.run(
                [host, "-m", "venv", env_dir],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode != 0:
                self.error.emit(f"虚拟环境创建失败: {result.stderr.strip()}")
                return
            if not os.path.isfile(python_exe):
                self.error.emit("虚拟环境创建后未找到 python3")
                return
        else:
            self.progress.emit("虚拟环境已存在，检查依赖...", 30)

        if self.isInterruptionRequested():
            return

        # ── Step 2: Upgrade pip (venv ships pip; no get-pip bootstrap needed) ──
        self.progress.emit("正在升级 pip...", 40)
        subprocess.run(
            [python_exe, "-m", "pip", "install", "--upgrade", "pip",
             *_pip_index_args()],
            capture_output=True, text=True, timeout=180,
        )

        if self.isInterruptionRequested():
            return

        # ── Step 3: Install packages ──
        self.progress.emit("正在安装 onnxruntime, numpy, Pillow...", 55)
        result = subprocess.run(
            [python_exe, "-m", "pip", "install",
             "--no-warn-script-location",
             *REQUIRED_PACKAGES,
             *_pip_index_args()],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            self.error.emit(f"依赖安装失败: {result.stderr.strip()}")
            return

        if self.isInterruptionRequested():
            return

        # ── Step 4: Validate ──
        self.progress.emit("正在验证环境...", 95)
        if not is_env_usable(python_exe):
            self.error.emit("环境验证失败：onnxruntime 无法在虚拟环境中加载")
            return

        self.progress.emit("✓ 环境配置完成", 100)
        self.finished.emit(python_exe)

    @staticmethod
    def _patch_pth(env_dir: str) -> None:
        """Uncomment 'import site' in the ._pth file so pip/site-packages work."""
        for f in os.listdir(env_dir):
            if f.endswith("._pth"):
                pth_path = os.path.join(env_dir, f)
                with open(pth_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
                if "#import site" in content:
                    content = content.replace("#import site", "import site")
                    with open(pth_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                break
