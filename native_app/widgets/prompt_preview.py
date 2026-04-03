"""Prompt Preview — popup showing the fully assembled prompt before sending."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..logic import estimate_text_tokens
from ..theme import _fs, current_palette


ROLE_COLORS = {
    'system':    '#7c8a99',
    'user':      '#5090d0',
    'assistant': '#50a060',
}

ROLE_COLORS_LIGHT = {
    'system':    '#5a6670',
    'user':      '#3070b0',
    'assistant': '#3a7a48',
}


class PromptPreviewPopup(QWidget):
    """Read-only popup showing the assembled message list with token counts."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(480)

        p = current_palette()

        self._surface = QWidget(self)
        self._surface.setObjectName("PreviewSurface")
        self._surface.setStyleSheet(f"""
            #PreviewSurface {{
                background: {p['bg']};
                border: 1px solid {p['line_strong']};
                border-radius: 8px;
            }}
        """)

        self._layout = QVBoxLayout(self._surface)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)

        # Header
        self._header = QLabel(self._surface)
        self._header.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_12')}; font-weight: bold; background: transparent;"
        )
        self._layout.addWidget(self._header)

        # Scroll area for message sections
        scroll = QScrollArea(self._surface)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        self._scroll_content = QWidget()
        self._sections_layout = QVBoxLayout(self._scroll_content)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(4)
        scroll.setWidget(self._scroll_content)
        self._layout.addWidget(scroll, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._surface)

    def set_messages(self, messages: list[dict[str, str]], title: str = "Prompt Preview") -> None:
        """Populate the popup with message sections."""
        # Clear existing sections
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        p = current_palette()
        from ..theme import is_theme_light
        role_colors = ROLE_COLORS_LIGHT if is_theme_light() else ROLE_COLORS

        total_tokens = 0
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            tokens = estimate_text_tokens(content)
            total_tokens += tokens + 4  # 4 tokens overhead per message

            section = QWidget(self._scroll_content)
            sl = QVBoxLayout(section)
            sl.setContentsMargins(0, 0, 0, 0)
            sl.setSpacing(2)

            # Role header row
            header_row = QHBoxLayout()
            header_row.setContentsMargins(0, 0, 0, 0)
            role_label = QLabel(role.upper(), section)
            rc = role_colors.get(role, p['text_muted'])
            role_label.setStyleSheet(
                f"color: {rc}; font-size: {_fs('fs_10')}; font-weight: bold; "
                f"letter-spacing: 1px; background: transparent;"
            )
            header_row.addWidget(role_label)
            header_row.addStretch()
            tk_label = QLabel(f"{tokens} tk", section)
            tk_label.setStyleSheet(
                f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; background: transparent;"
            )
            header_row.addWidget(tk_label)
            sl.addLayout(header_row)

            # Content preview
            preview = QTextEdit(section)
            preview.setReadOnly(True)
            preview.setPlainText(content)
            # Limit height
            line_count = content.count('\n') + 1
            height = min(max(40, line_count * 16 + 12), 120)
            preview.setFixedHeight(height)
            preview.setStyleSheet(f"""
                QTextEdit {{
                    background: {p['bg_content']};
                    color: {p['text_muted']};
                    border: 1px solid {p['line']};
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-size: {_fs('fs_11')};
                }}
            """)
            sl.addWidget(preview)

            self._sections_layout.addWidget(section)

        self._sections_layout.addStretch()

        # Update header with total
        total_tokens += 2  # array overhead
        self._header.setText(f"{title}    {total_tokens} tokens")

        # Auto-size height
        section_count = len(messages)
        target_h = min(max(200, section_count * 100 + 60), 600)
        self.setFixedHeight(target_h)

    def show_at(self, global_pos: QPoint) -> None:
        """Show popup near the given global position, clamped to screen."""
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = global_pos.x() - self.width() // 2
            y = global_pos.y() - self.height() - 8
            # Clamp
            x = max(avail.left() + 4, min(x, avail.right() - self.width() - 4))
            if y < avail.top() + 4:
                y = global_pos.y() + 20  # Show below if no room above
            self.move(x, y)
        else:
            self.move(global_pos - QPoint(self.width() // 2, self.height() + 8))
        self.show()
