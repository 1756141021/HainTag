"""Auto-update checker — queries GitHub Releases API."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from typing import Any

from PyQt6.QtCore import QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import _fs, current_palette
from .ui_tokens import _dp

_GITHUB_API = "https://api.github.com/repos/1756141021/HainTag/releases/latest"
_GITHUB_RELEASES_PAGE = "https://github.com/1756141021/HainTag/releases"


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse 'v0.5.21' or '0.5.21' into a comparable tuple."""
    cleaned = tag.lstrip("vV")
    parts = re.split(r"[.\-]", cleaned)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            break
    return tuple(result) or (0,)


class UpdateChecker(QThread):
    """Background thread that checks GitHub for a newer release."""

    update_available = pyqtSignal(str, str, str)  # version, changelog, download_url
    no_update = pyqtSignal()
    check_error = pyqtSignal(str)

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self._current = current_version

    def run(self):
        try:
            # Try httpx first, fall back to requests
            data = self._fetch()
            if data is None:
                return

            tag = data.get("tag_name", "")
            body = data.get("body", "")
            assets = data.get("assets", [])
            download_url = _GITHUB_RELEASES_PAGE
            if assets:
                download_url = assets[0].get("browser_download_url", download_url)

            remote = _parse_version(tag)
            local = _parse_version(self._current)

            if remote > local:
                self.update_available.emit(tag, body, download_url)
            else:
                self.no_update.emit()

        except Exception as exc:
            self.check_error.emit(str(exc))

    def _fetch(self) -> dict[str, Any] | None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"HainTag/{self._current}",
        }
        try:
            import httpx
            with httpx.Client(timeout=10) as client:
                resp = client.get(_GITHUB_API, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except ImportError:
            pass
        try:
            import requests
            resp = requests.get(_GITHUB_API, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except ImportError:
            pass
        # Last resort: urllib
        import urllib.request
        req = urllib.request.Request(_GITHUB_API, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))


class UpdateDownloadWorker(QThread):
    """Downloads update ZIP, validates, and extracts."""

    progress = pyqtSignal(str, int)
    download_done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url: str, translator, parent=None):
        super().__init__(parent)
        self._url = url
        self._t = translator
        self._cancelled = False
        self._temp_dir = ""

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._temp_dir = tempfile.mkdtemp(prefix="haintag_update_")
            zip_path = os.path.join(self._temp_dir, "update.zip")

            self._download(zip_path)
            if self._cancelled:
                self._cleanup()
                return

            self.progress.emit(self._t.t("update_validating"), 82)
            with zipfile.ZipFile(zip_path, "r") as zf:
                bad = zf.testzip()
                if bad:
                    raise RuntimeError(f"Corrupt file in ZIP: {bad}")
                names = [n.lower().replace("\\", "/") for n in zf.namelist()]
                if not any(n == "haintag/haintag.exe" for n in names):
                    raise RuntimeError("HainTag.exe not found in ZIP")

            if self._cancelled:
                self._cleanup()
                return

            self.progress.emit(self._t.t("update_extracting"), 90)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self._temp_dir)

            os.remove(zip_path)
            self.progress.emit(self._t.t("update_ready"), 100)
            self.download_done.emit(self._temp_dir)

        except Exception as exc:
            self._cleanup()
            if not self._cancelled:
                self.error.emit(str(exc))

    def _cleanup(self):
        if self._temp_dir and os.path.isdir(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = ""

    def _download(self, zip_path: str) -> None:
        self.progress.emit(self._t.t("update_downloading"), 0)
        headers = {"User-Agent": "HainTag-Updater/1.0"}

        try:
            import httpx
            with httpx.stream("GET", self._url, headers=headers,
                              timeout=120, follow_redirects=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                self._write_stream(zip_path, resp.iter_bytes(8192), total)
            return
        except ImportError:
            pass

        try:
            import requests as req_lib
            with req_lib.get(self._url, headers=headers,
                             stream=True, timeout=120) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                self._write_stream(zip_path, resp.iter_content(8192), total)
            return
        except ImportError:
            pass

        import urllib.request
        req = urllib.request.Request(self._url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=120)
        total = int(resp.headers.get("Content-Length", 0))

        def _chunks():
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                yield chunk

        self._write_stream(zip_path, _chunks(), total)

    def _write_stream(self, zip_path: str, chunks, total: int) -> None:
        label = self._t.t("update_downloading")
        downloaded = 0
        with open(zip_path, "wb") as f:
            for chunk in chunks:
                if self._cancelled:
                    return
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded * 80 / total)
                    mb_d = downloaded / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    self.progress.emit(
                        f"{label} ({mb_d:.1f}/{mb_t:.1f} MB)", pct
                    )


def _generate_update_script(pid: int, source_dir: str,
                            target_dir: str, exe_path: str) -> str:
    """Write a batch script with baked-in paths and return its path."""
    content = (
        '@echo off\n'
        'chcp 65001 >nul 2>&1\n'
        ':wait\n'
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul && '
        '(timeout /t 1 /nobreak >nul & goto wait)\n'
        'timeout /t 1 /nobreak >nul\n'
        f'robocopy "{source_dir}\\HainTag" "{target_dir}" '
        '/MIR /R:3 /W:2 /NP /NFL /NDL /NJH /NJS\n'
        'if %errorlevel% GTR 7 (echo Update failed & pause & goto end)\n'
        f'start "" "{exe_path}"\n'
        ':end\n'
        f'rd /s /q "{source_dir}" >nul 2>&1\n'
        '(goto) 2>nul & del "%~f0"\n'
    )
    path = os.path.join(tempfile.gettempdir(), "haintag_update.bat")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class UpdateDialog(QDialog):
    """Dialog showing available update with changelog."""

    SKIP = "skip"
    LATER = "later"
    UPDATE = "update"

    def __init__(self, version: str, changelog: str, download_url: str,
                 translator, parent=None):
        super().__init__(parent)
        self._download_url = download_url
        self._result_action = self.LATER
        self._t = translator
        self._extracted_dir = ""
        self._downloading = False
        self._worker = None

        p = current_palette()
        self.setWindowTitle(translator.t("update_title"))
        self.setFixedWidth(_dp(480))
        self.setStyleSheet(f"background: {p['bg']}; color: {p['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(_dp(12))
        layout.setContentsMargins(_dp(20), _dp(20), _dp(20), _dp(20))

        # Title
        title = QLabel(f"{translator.t('update_found')}  {version}", self)
        title.setStyleSheet(
            f"font-size: {_fs('fs_14')}; font-weight: bold; color: {p['text']};"
        )
        layout.addWidget(title)

        # Changelog
        if changelog:
            cl_edit = QTextEdit(self)
            cl_edit.setPlainText(changelog)
            cl_edit.setReadOnly(True)
            cl_edit.setMaximumHeight(_dp(250))
            cl_edit.setStyleSheet(
                f"background: {p['bg_input']}; color: {p['text']}; "
                f"border: 1px solid {p['line']}; border-radius: 4px; "
                f"font-size: {_fs('fs_10')}; padding: 8px;"
            )
            layout.addWidget(cl_edit)

        # Buttons
        self._btn_widget = QWidget(self)
        btn_row = QHBoxLayout(self._btn_widget)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(_dp(10))
        btn_row.addStretch()

        skip_btn = QPushButton(translator.t("update_skip"), self)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px 16px; font-size: {_fs('fs_10')};"
        )
        skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(skip_btn)

        later_btn = QPushButton(translator.t("update_later"), self)
        later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        later_btn.setStyleSheet(
            f"color: {p['text']}; background: transparent; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px 16px; font-size: {_fs('fs_10')};"
        )
        later_btn.clicked.connect(self._on_later)
        btn_row.addWidget(later_btn)

        update_btn = QPushButton(translator.t("update_now"), self)
        update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_btn.setStyleSheet(
            f"color: {p['accent_text']}; background: {p['accent']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 6px 20px; font-size: {_fs('fs_11')}; font-weight: bold;"
        )
        update_btn.clicked.connect(self._on_update)
        btn_row.addWidget(update_btn)

        layout.addWidget(self._btn_widget)

        # Download progress (hidden initially)
        self._progress_label = QLabel(self)
        self._progress_label.setWordWrap(True)
        self._progress_label.setStyleSheet(
            f"font-size: {_fs('fs_10')}; color: {p['text']};"
        )
        self._progress_label.hide()
        layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(_dp(6))
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {p['bg_input']}; border: none; border-radius: 3px; }} "
            f"QProgressBar::chunk {{ background: {p['accent']}; border-radius: 3px; }}"
        )
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        self._cancel_btn = QPushButton(translator.t("update_download_cancel"), self)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            f"color: {p['text']}; background: transparent; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px 16px; font-size: {_fs('fs_10')};"
        )
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.hide()
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

    @property
    def result_action(self) -> str:
        return self._result_action

    @property
    def extracted_dir(self) -> str:
        return self._extracted_dir

    @property
    def version(self) -> str:
        return self.windowTitle()

    def _on_skip(self):
        self._result_action = self.SKIP
        self.accept()

    def _on_later(self):
        self._result_action = self.LATER
        self.accept()

    def _on_update(self):
        if not getattr(sys, "frozen", False):
            self._result_action = self.UPDATE
            QDesktopServices.openUrl(QUrl(self._download_url))
            self.accept()
            return
        self._downloading = True
        self._btn_widget.hide()
        self._progress_label.show()
        self._progress_bar.show()
        self._cancel_btn.show()
        self._worker = UpdateDownloadWorker(self._download_url, self._t, self)
        self._worker.progress.connect(self._on_dl_progress)
        self._worker.download_done.connect(self._on_dl_done)
        self._worker.error.connect(self._on_dl_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_dl_progress(self, message: str, percent: int):
        self._progress_label.setText(message)
        self._progress_bar.setValue(percent)

    def _on_dl_done(self, extracted_dir: str):
        self._downloading = False
        self._extracted_dir = extracted_dir
        self._result_action = self.UPDATE
        self.accept()

    def _on_dl_error(self, message: str):
        self._downloading = False
        self._progress_bar.hide()
        self._cancel_btn.hide()
        self._progress_label.setText(
            f"{self._t.t('update_download_failed')}: {message}"
        )
        p = current_palette()
        close_btn = QPushButton(self._t.t("update_later"), self)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"color: {p['text']}; background: transparent; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px 16px; font-size: {_fs('fs_10')};"
        )
        close_btn.clicked.connect(self.reject)
        self.layout().addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_cancel(self):
        if self._worker:
            self._cancel_btn.setEnabled(False)
            self._worker.cancel()

    def _on_worker_finished(self):
        if self._downloading:
            self._downloading = False
            self.reject()

    def closeEvent(self, event):
        if self._downloading:
            event.ignore()
        else:
            super().closeEvent(event)


class NoUpdateDialog(QDialog):
    """Simple dialog shown when already up to date."""

    def __init__(self, current_version: str, translator, parent=None):
        super().__init__(parent)
        p = current_palette()
        self.setWindowTitle(translator.t("update_title"))
        self.setFixedWidth(_dp(320))
        self.setStyleSheet(f"background: {p['bg']}; color: {p['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(_dp(12))
        layout.setContentsMargins(_dp(20), _dp(20), _dp(20), _dp(20))

        label = QLabel(f"{translator.t('update_up_to_date')}  v{current_version}", self)
        label.setStyleSheet(f"font-size: {_fs('fs_12')}; color: {p['text']};")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        ok_btn = QPushButton("OK", self)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(
            f"color: {p['text']}; background: {p['accent']}; "
            f"border: none; border-radius: 4px; padding: 6px 20px; font-size: {_fs('fs_10')};"
        )
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)
