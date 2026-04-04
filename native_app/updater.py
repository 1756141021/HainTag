"""Auto-update checker — queries GitHub Releases API."""
from __future__ import annotations

import json
import re
from typing import Any

from PyQt6.QtCore import QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import _fs, current_palette

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

        p = current_palette()
        self.setWindowTitle(translator.t("update_title"))
        self.setFixedWidth(480)
        self.setStyleSheet(f"background: {p['bg']}; color: {p['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

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
            cl_edit.setMaximumHeight(250)
            cl_edit.setStyleSheet(
                f"background: {p['bg_input']}; color: {p['text']}; "
                f"border: 1px solid {p['line']}; border-radius: 4px; "
                f"font-size: {_fs('fs_10')}; padding: 8px;"
            )
            layout.addWidget(cl_edit)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
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

        layout.addLayout(btn_row)

    @property
    def result_action(self) -> str:
        return self._result_action

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
        self._result_action = self.UPDATE
        QDesktopServices.openUrl(QUrl(self._download_url))
        self.accept()


class NoUpdateDialog(QDialog):
    """Simple dialog shown when already up to date."""

    def __init__(self, current_version: str, translator, parent=None):
        super().__init__(parent)
        p = current_palette()
        self.setWindowTitle(translator.t("update_title"))
        self.setFixedWidth(320)
        self.setStyleSheet(f"background: {p['bg']}; color: {p['text']};")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

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
