from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter
from PyQt6.QtWidgets import QCheckBox, QLabel

from ..theme import is_theme_light


def compute_resized_rect(
    origin: QRect,
    direction: str,
    delta: QPoint,
    bounds: QRect,
    min_width: int,
    min_height: int,
) -> QRect:
    """Compute a new rectangle after a directional resize, clamped to bounds and minimum size."""
    left = origin.left()
    top = origin.top()
    right = origin.right()
    bottom = origin.bottom()

    if 'left' in direction:
        left += delta.x()
    if 'right' in direction:
        right += delta.x()
    if 'top' in direction:
        top += delta.y()
    if 'bottom' in direction:
        bottom += delta.y()

    if 'left' in direction:
        left = min(left, right - min_width + 1)
    elif 'right' in direction:
        right = max(right, left + min_width - 1)

    if 'top' in direction:
        top = min(top, bottom - min_height + 1)
    elif 'bottom' in direction:
        bottom = max(bottom, top + min_height - 1)

    if bounds.isValid():
        if 'left' in direction:
            left = max(bounds.left(), left)
            if right - left + 1 < min_width:
                left = max(bounds.left(), right - min_width + 1)
        elif 'right' in direction:
            right = min(bounds.right(), right)
            if right - left + 1 < min_width:
                right = min(bounds.right(), left + min_width - 1)

        if 'top' in direction:
            top = max(bounds.top(), top)
            if bottom - top + 1 < min_height:
                top = max(bounds.top(), bottom - min_height + 1)
        elif 'bottom' in direction:
            bottom = min(bounds.bottom(), bottom)
            if bottom - top + 1 < min_height:
                bottom = min(bounds.bottom(), top + min_height - 1)

    return QRect(left, top, right - left + 1, bottom - top + 1)


class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(36, 18)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        light = is_theme_light()
        if self.isChecked():
            track_color = QColor(80, 100, 180, 50) if light else QColor(100, 120, 220, 70)
            knob_color = QColor(80, 90, 160) if light else QColor(122, 122, 204)
        else:
            track_color = QColor(0, 0, 0, 18) if light else QColor(255, 255, 255, 18)
            knob_color = QColor(160, 160, 165) if light else QColor(74, 74, 106)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(self.rect(), 9, 9)
        x = 20 if self.isChecked() else 2
        painter.setBrush(knob_color)
        painter.drawEllipse(x, 2, 14, 14)
        painter.end()

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)


class DragHandleLabel(QLabel):
    drag_started = pyqtSignal()

    def __init__(self, text: str = "≡", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._press_pos = QPoint()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            if (event.pos() - self._press_pos).manhattanLength() >= 6:
                self.drag_started.emit()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)
