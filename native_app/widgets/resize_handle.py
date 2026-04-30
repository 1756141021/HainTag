"""Reusable vertical resize handle for QTextEdit height adjustment."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QTextEdit, QVBoxLayout, QWidget

from ..theme import current_palette
from ..ui_tokens import _dp


class ResizeHandle(QFrame):
    """6px draggable bar placed below a QTextEdit to resize its height."""

    def __init__(self, target: QTextEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target = target
        self._dragging = False
        self._start_y = 0.0
        self._start_h = 0
        self.setFixedHeight(_dp(6))
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self._apply_style()

    def _apply_style(self) -> None:
        p = current_palette()
        self.setStyleSheet(
            f"background: {p['line']}; border-radius: 2px; margin: 0 30%;"
        )

    def apply_theme(self) -> None:
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_y = event.globalPosition().y()
            self._start_h = self._target.maximumHeight()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            delta = int(event.globalPosition().y() - self._start_y)
            new_h = max(40, self._start_h + delta)
            self._target.setMaximumHeight(new_h)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        event.accept()


def wrap_with_resize_handle(text_edit: QTextEdit, parent: QWidget | None = None) -> QWidget:
    """Wrap a QTextEdit in a container with a resize handle at the bottom.

    Returns the container widget (add this to layouts instead of the raw QTextEdit).
    """
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(text_edit)
    handle = ResizeHandle(text_edit, container)
    layout.addWidget(handle)
    container._resize_handle = handle  # keep reference for theme updates
    return container
