"""HintManager — first-time-use hint bubbles for feature discoverability.

Provides a reusable framework: register a hint on a widget, and it shows
a styled tooltip bubble once (persisted). Future hints are added by calling
hint_manager.register() on target widgets.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QPropertyAnimation, QEasingCurve, QTimer, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..i18n import Translator
from ..storage import AppStorage
from ..theme import _fs, current_palette
from ..ui_tokens import _dp


class HintBubble(QWidget):
    """A small floating tooltip bubble that auto-dismisses."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent,
                         Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        p = current_palette()
        surface = QWidget(self)
        surface.setStyleSheet(
            f"background: {p['bg_surface']}; border: 1px solid {p['line_strong']}; "
            f"border-radius: 4px;"
        )

        layout = QHBoxLayout(surface)
        layout.setContentsMargins(_dp(10), _dp(6), _dp(10), _dp(6))
        layout.setSpacing(_dp(8))

        lbl = QLabel(text, surface)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_11')}; background: transparent; border: none;"
        )
        layout.addWidget(lbl, 1)

        got_it_btn = QPushButton("OK", surface)
        got_it_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        got_it_btn.setStyleSheet(
            f"color: {p['accent_text']}; background: {p['accent']}; border: none; "
            f"border-radius: 3px; padding: 2px 10px; font-size: {_fs('fs_9')};"
        )
        got_it_btn.clicked.connect(self.close)
        layout.addWidget(got_it_btn)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(surface)
        self.adjustSize()
        self.setFixedWidth(min(_dp(300), self.sizeHint().width() + _dp(20)))

    def show_near(self, widget: QWidget, position: str = "below") -> None:
        """Position the bubble near the target widget, clamped to screen."""
        try:
            ref = widget.mapToGlobal(QPoint(0, 0))
        except RuntimeError:
            return
        w_size = widget.size()

        if position == "below":
            x = ref.x() + w_size.width() // 2 - self.width() // 2
            y = ref.y() + w_size.height() + 6
        elif position == "above":
            x = ref.x() + w_size.width() // 2 - self.width() // 2
            y = ref.y() - self.height() - 6
        elif position == "left":
            x = ref.x() - self.width() - 6
            y = ref.y() + w_size.height() // 2 - self.height() // 2
        elif position == "right":
            x = ref.x() + w_size.width() + 6
            y = ref.y() + w_size.height() // 2 - self.height() // 2
        else:
            x, y = ref.x(), ref.y() + w_size.height() + 6

        # Clamp to screen
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = max(avail.left() + 4, min(x, avail.right() - self.width() - 4))
            y = max(avail.top() + 4, min(y, avail.bottom() - self.height() - 4))

        self.move(x, y)
        self.setWindowOpacity(0.0)
        self.show()

        # Fade in
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def mousePressEvent(self, event):
        pass  # Only dismiss via OK button


class HintManager:
    """Manages first-time-use hints. Tracks which hints have been shown (persisted).

    Usage:
        hint_manager = HintManager(storage, translator)
        hint_manager.register(some_widget, "scrub_weight", "hint_scrub_weight", position="above")
    """

    def __init__(self, storage: AppStorage, translator: Translator) -> None:
        self._storage = storage
        self._translator = translator
        self._shown: set[str] = storage.load_shown_hints()
        self._active_bubbles: list[HintBubble] = []
        self._pending: list[tuple] = []

    def register(self, widget: QWidget, hint_id: str, text_key: str,
                 position: str = "below", delay_ms: int = 1000) -> None:
        """Register a hint on a widget. Shows once on first encounter."""
        if hint_id in self._shown:
            return
        self._pending.append((widget, hint_id, text_key, position))
        QTimer.singleShot(delay_ms, lambda: self._try_show(widget, hint_id, text_key, position))

    def _try_show(self, widget: QWidget, hint_id: str, text_key: str, position: str) -> None:
        try:
            import sip
            if sip.isdeleted(widget):
                return
        except ImportError:
            pass
        if hint_id in self._shown:
            return
        if not widget.isVisible():
            # Retry later — widget might become visible
            QTimer.singleShot(3000, lambda: self._try_show(widget, hint_id, text_key, position))
            return
        text = self._translator.t(text_key)
        if not text or text == text_key:
            text = text_key
        bubble = HintBubble(text)
        bubble.show_near(widget, position)
        self._active_bubbles.append(bubble)
        self._shown.add(hint_id)
        self._storage.save_shown_hints(self._shown)

    def show_hint(self, widget: QWidget, hint_id: str, text_key: str,
                  position: str = "below") -> None:
        """Force-show a hint regardless of whether it was shown before."""
        text = self._translator.t(text_key)
        bubble = HintBubble(text)
        bubble.show_near(widget, position)
        self._active_bubbles.append(bubble)

    def reset_hints(self) -> None:
        """Clear all shown hints — they will appear again."""
        self._shown.clear()
        self._storage.save_shown_hints(self._shown)

    def dismiss(self, hint_id: str) -> None:
        """Mark a hint as shown without displaying it."""
        self._shown.add(hint_id)
        self._storage.save_shown_hints(self._shown)

    def is_shown(self, hint_id: str) -> bool:
        return hint_id in self._shown
