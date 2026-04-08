"""Embedded Python environment manager for onnxruntime subprocess fallback.

Downloads and sets up a standalone Python 3.12 embeddable package with
onnxruntime, numpy, and Pillow when the host Python can't load onnxruntime.
"""
from __future__ import annotations

import locale
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from PyQt6.QtCore import QThread, pyqtSignal

# ── Constants ──

PYTHON_VERSION = "3.12.8"
PYTHON_EMBED_ZIP = f"python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{PYTHON_EMBED_ZIP}"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
REQUIRED_PACKAGES = ["onnxruntime", "numpy", "Pillow"]

# pip mirror for Chinese locale
_TSINGHUA_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _env_dir() -> str:
    """Return the embedded Python environment directory path."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    return os.path.join(appdata, "HainTag", "python_env")


def get_embedded_python_path() -> str | None:
    """Return path to embedded python.exe if it exists, else None."""
    python_exe = os.path.join(_env_dir(), "python.exe")
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
    finished = pyqtSignal(str)        # python.exe path
    error = pyqtSignal(str)           # error message

    def run(self):
        try:
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
