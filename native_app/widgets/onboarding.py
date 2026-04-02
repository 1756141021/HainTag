"""Onboarding — step-by-step highlight tour for first-time users.

Shows a semi-transparent overlay with a highlighted cutout around the target
widget, a description panel, and Next/Skip buttons.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QPropertyAnimation, QEasingCurve, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QRegion
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..i18n import Translator
from ..theme import _fs, current_palette


@dataclass
class OnboardingStep:
    widget: QWidget | None  # target widget to highlight (None = center text only)
    title: str
    description: str
    position: str = "below"  # below / above / left / right


class OnboardingOverlay(QWidget):
    """Full-window overlay that highlights one widget at a time with a description."""

    finished = pyqtSignal()

    def __init__(self, parent: QWidget, translator: Translator) -> None:
        super().__init__(parent)
        self._translator = translator
        self._steps: list[OnboardingStep] = []
        self._current = 0
        self.setObjectName("OnboardingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.hide()

        # Description panel
        self._panel = QWidget(self)
        self._panel.setObjectName("OnboardingPanel")

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(20, 16, 20, 12)
        panel_layout.setSpacing(8)

        self._title_label = QLabel(self._panel)
        self._title_label.setObjectName("OnboardingTitle")
        self._title_label.setWordWrap(True)
        panel_layout.addWidget(self._title_label)

        self._desc_label = QLabel(self._panel)
        self._desc_label.setObjectName("OnboardingDesc")
        self._desc_label.setWordWrap(True)
        panel_layout.addWidget(self._desc_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._step_label = QLabel(self._panel)
        self._step_label.setObjectName("OnboardingStep")
        btn_row.addWidget(self._step_label)
        btn_row.addStretch()

        self._skip_btn = QPushButton(self._panel)
        self._skip_btn.setObjectName("OnboardingSkip")
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.clicked.connect(self._finish)
        btn_row.addWidget(self._skip_btn)

        self._next_btn = QPushButton(self._panel)
        self._next_btn.setObjectName("OnboardingNext")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._next_step)
        btn_row.addWidget(self._next_btn)

        panel_layout.addLayout(btn_row)
        self._panel.setFixedWidth(340)

    def set_steps(self, steps: list[OnboardingStep]) -> None:
        self._steps = steps

    def start(self) -> None:
        if not self._steps:
            return
        self._current = 0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._show_step()

    def _show_step(self) -> None:
        if self._current >= len(self._steps):
            self._finish()
            return

        step = self._steps[self._current]
        p = current_palette()

        self._title_label.setText(step.title)
        self._title_label.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_13')}; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._desc_label.setText(step.description)
        self._desc_label.setStyleSheet(
            f"color: {p['text_muted']}; font-size: {_fs('fs_11')}; "
            f"background: transparent; border: none;"
        )
        self._step_label.setText(f"{self._current + 1} / {len(self._steps)}")
        self._step_label.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; "
            f"background: transparent; border: none;"
        )
        is_last = self._current >= len(self._steps) - 1
        self._skip_btn.setText(self._translator.t("onboarding_skip"))
        self._skip_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; border: none; "
            f"font-size: {_fs('fs_10')}; padding: 4px 8px;"
        )
        self._skip_btn.setVisible(not is_last)
        next_text = self._translator.t("onboarding_finish") if is_last else self._translator.t("onboarding_next")
        self._next_btn.setText(next_text)
        self._next_btn.setStyleSheet(
            f"color: {p['accent_text']}; background: {p['accent']}; border: none; "
            f"border-radius: 4px; font-size: {_fs('fs_11')}; padding: 6px 16px;"
        )

        self._panel.setStyleSheet(
            f"#OnboardingPanel {{ background: {p['bg_surface']}; "
            f"border: 1px solid {p['line_strong']}; border-radius: 8px; }}"
        )
        self._panel.adjustSize()
        self._position_panel(step)
        self.update()  # repaint overlay

    def _position_panel(self, step: OnboardingStep) -> None:
        if step.widget is None or not step.widget.isVisible():
            # Center in parent
            px = (self.width() - self._panel.width()) // 2
            py = (self.height() - self._panel.height()) // 2
        else:
            try:
                ref = step.widget.mapTo(self.parentWidget(), QPoint(0, 0))
            except RuntimeError:
                px = (self.width() - self._panel.width()) // 2
                py = (self.height() - self._panel.height()) // 2
                self._panel.move(px, py)
                return
            w_rect = QRect(ref, step.widget.size())
            margin = 12

            if step.position == "below":
                px = w_rect.center().x() - self._panel.width() // 2
                py = w_rect.bottom() + margin
            elif step.position == "above":
                px = w_rect.center().x() - self._panel.width() // 2
                py = w_rect.top() - self._panel.height() - margin
            elif step.position == "left":
                px = w_rect.left() - self._panel.width() - margin
                py = w_rect.center().y() - self._panel.height() // 2
            elif step.position == "right":
                px = w_rect.right() + margin
                py = w_rect.center().y() - self._panel.height() // 2
            else:
                px = w_rect.center().x() - self._panel.width() // 2
                py = w_rect.bottom() + margin

            # Clamp to overlay bounds
            px = max(8, min(px, self.width() - self._panel.width() - 8))
            py = max(8, min(py, self.height() - self._panel.height() - 8))

        self._panel.move(px, py)

    def _next_step(self) -> None:
        self._current += 1
        if self._current >= len(self._steps):
            self._finish()
        else:
            self._show_step()

    def _finish(self) -> None:
        self.hide()
        self._current = 0
        self.finished.emit()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent overlay
        overlay_color = QColor(0, 0, 0, 160)

        if self._current < len(self._steps):
            step = self._steps[self._current]
            if step.widget is not None and step.widget.isVisible():
                try:
                    ref = step.widget.mapTo(self.parentWidget(), QPoint(0, 0))
                    highlight = QRect(ref, step.widget.size()).adjusted(-6, -6, 6, 6)
                except RuntimeError:
                    highlight = None
            else:
                highlight = None
        else:
            highlight = None

        if highlight is not None:
            # Draw overlay with cutout
            path = QPainterPath()
            path.addRect(0, 0, self.width(), self.height())
            cutout = QPainterPath()
            cutout.addRoundedRect(float(highlight.x()), float(highlight.y()),
                                  float(highlight.width()), float(highlight.height()), 8, 8)
            path = path.subtracted(cutout)
            painter.fillPath(path, overlay_color)
            # Highlight border
            painter.setPen(QColor(current_palette()['accent_text']))
            painter.drawRoundedRect(highlight, 8, 8)
        else:
            painter.fillRect(self.rect(), overlay_color)

        painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible() and self._current < len(self._steps):
            self._position_panel(self._steps[self._current])

    def mousePressEvent(self, event) -> None:
        event.accept()  # Eat all clicks on overlay
