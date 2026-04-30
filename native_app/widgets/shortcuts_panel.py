"""Shortcuts Panel — popup cheat sheet for all keyboard shortcuts and gestures."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..models import SEND_MODE_CTRL_ENTER, SEND_MODE_ENTER
from ..theme import _fs, current_palette
from ..ui_tokens import _dp

def _shortcut_data(send_mode: str) -> list[tuple[str, list[tuple[str, str]]]]:
    send_label = "Enter" if send_mode == SEND_MODE_ENTER else "Ctrl+Enter"
    return [
    ("shortcut_global", [
        (send_label, "sc_send"),
        ("Ctrl+Shift+S", "sc_summary"),
        ("Esc", "sc_escape"),
        ("F1  /  Ctrl+/", "sc_shortcuts"),
    ]),
    ("shortcut_image_manager", [
        ("F2", "sc_rename"),
        ("Delete", "sc_delete"),
        ("Ctrl+X", "sc_cut"),
        ("Ctrl+V", "sc_paste"),
        ("Ctrl+C", "sc_copy"),
        ("Alt+\u2190 / \u2192 / \u2191", "sc_nav_back"),
        ("Enter", "sc_open"),
    ]),
    ("shortcut_lightbox", [
        ("Esc  /  Q", "sc_close_lightbox"),
        ("\u2190  /  A", "sc_prev_image"),
        ("\u2192  /  D", "sc_next_image"),
    ]),
    ("shortcut_autocomplete", [
        ("\u2191 \u2193", "sc_suggest_nav"),
        ("Enter  /  Tab", "sc_suggest_accept"),
        ("Esc", "sc_suggest_dismiss"),
    ]),
    ("shortcut_output", [
        ("Right-click drag", "sc_scrub_weight"),
    ]),
    ("shortcut_card", [
        ("\ud83d\udccc", "sc_pin_card"),
        ("Right-click grip", "sc_dock_card"),
    ]),
]


class ShortcutsPanel(QWidget):
    """Popup panel showing all keyboard shortcuts and mouse gestures."""

    def __init__(self, translator: Translator, send_mode: str = SEND_MODE_ENTER, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(_dp(400))

        p = current_palette()
        t = translator.t

        surface = QWidget(self)
        surface.setStyleSheet(
            f"#ShortcutSurface {{ background: {p['bg']}; "
            f"border: 1px solid {p['line_strong']}; border-radius: 8px; }}"
        )
        surface.setObjectName("ShortcutSurface")

        main_layout = QVBoxLayout(surface)
        main_layout.setContentsMargins(_dp(16), _dp(12), _dp(16), _dp(12))
        main_layout.setSpacing(_dp(8))

        # Header
        header = QLabel(t("shortcuts"), surface)
        header.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_13')}; font-weight: bold; "
            f"background: transparent; letter-spacing: 1px;"
        )
        main_layout.addWidget(header)

        # Scroll area
        scroll = QScrollArea(surface)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, _dp(4), 0, _dp(4))
        cl.setSpacing(_dp(12))

        shortcut_data = _shortcut_data(send_mode)

        for cat_key, shortcuts in shortcut_data:
            # Category header
            cat_label = QLabel(t(cat_key), content)
            cat_label.setStyleSheet(
                f"color: {p['accent_text']}; font-size: {_fs('fs_10')}; font-weight: bold; "
                f"letter-spacing: 2px; background: transparent;"
            )
            cl.addWidget(cat_label)

            for keys, desc_key in shortcuts:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(_dp(12))

                # Key badge
                key_label = QLabel(keys, content)
                key_label.setFixedWidth(_dp(140))
                key_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                key_label.setStyleSheet(
                    f"background: {p['bg_content']}; color: {p['text']}; "
                    f"border: 1px solid {p['line']}; border-radius: 3px; "
                    f"padding: 2px 8px; font-size: {_fs('fs_10')}; font-family: monospace;"
                )
                row.addWidget(key_label)

                # Description
                desc_label = QLabel(t(desc_key), content)
                desc_label.setStyleSheet(
                    f"color: {p['text_muted']}; font-size: {_fs('fs_11')}; background: transparent;"
                )
                row.addWidget(desc_label, 1)

                cl.addLayout(row)

        cl.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(surface)

        # Auto-size height
        section_count = sum(len(s) for _, s in shortcut_data) + len(shortcut_data)
        self.setFixedHeight(min(max(_dp(300), section_count * _dp(28) + _dp(80)), _dp(550)))

    def show_at(self, global_pos: QPoint) -> None:
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = global_pos.x() - self.width() // 2
            y = global_pos.y() - self.height() // 2
            x = max(avail.left() + 4, min(x, avail.right() - self.width() - 4))
            y = max(avail.top() + 4, min(y, avail.bottom() - self.height() - 4))
            self.move(x, y)
        else:
            self.move(global_pos)
        self.show()
