"""History Sidebar — collapsible panel on workspace right edge."""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, Qt, QPropertyAnimation, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..models import HistoryEntry
from ..storage import AppStorage
from ..theme import _fs, current_palette


class _HistorySidebarItem(QWidget):
    """Single collapsible history entry in the sidebar."""

    clicked = pyqtSignal(object)  # HistoryEntry
    fill_requested = pyqtSignal(str, str)  # output_text, nochar_text

    def __init__(self, entry: HistoryEntry, translator: Translator, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._t = translator
        self._collapsed = True
        self._body: QWidget | None = None  # lazy

        p = current_palette()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header (always visible) ──
        self._header = QWidget(self)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setFixedHeight(44)
        self._header.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {p['line']};"
        )
        hlayout = QVBoxLayout(self._header)
        hlayout.setContentsMargins(8, 4, 8, 4)
        hlayout.setSpacing(1)

        # Row 1: toggle + timestamp + model
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self._toggle_label = QLabel("▸", self._header)
        self._toggle_label.setFixedWidth(12)
        self._toggle_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; border: none;")
        top_row.addWidget(self._toggle_label)

        ts_display = entry.timestamp[:16].replace("T", "  ")
        self._ts_label = QLabel(ts_display, self._header)
        self._ts_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; border: none;")
        top_row.addWidget(self._ts_label)

        self._model_label = None
        if entry.model:
            self._model_label = QLabel(entry.model, self._header)
            self._model_label.setStyleSheet(
                f"color: {p['accent_text']}; font-size: {_fs('fs_9')}; border: none; "
                f"background: {p['accent']}; border-radius: 2px; padding: 0 4px;"
            )
            top_row.addWidget(self._model_label)
        top_row.addStretch()
        hlayout.addLayout(top_row)

        # Row 2: input preview
        preview = entry.input_text[:60].replace("\n", " ")
        if len(entry.input_text) > 60:
            preview += "…"
        self._preview_label = QLabel(preview, self._header)
        self._preview_label.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_9')}; border: none;"
        )
        hlayout.addWidget(self._preview_label)

        root.addWidget(self._header)

        self.setFixedHeight(44)

    # ── Toggle ──

    def toggle(self):
        if self._collapsed:
            self._expand()
        else:
            self._collapse()

    def _expand(self):
        self._collapsed = False
        self._toggle_label.setText("▾")
        if self._body is None:
            self._create_body()
        self._body.show()
        self.setFixedHeight(self._header.height() + self._body.sizeHint().height())
        self.updateGeometry()

    def _collapse(self):
        self._collapsed = True
        self._toggle_label.setText("▸")
        if self._body:
            self._body.hide()
        self.setFixedHeight(44)
        self.updateGeometry()

    def _create_body(self):
        """Lazy-create the expanded body with full content."""
        p = current_palette()
        self._body = QWidget(self)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(8, 4, 8, 8)
        body_layout.setSpacing(4)

        # Full user input
        self._input_label = QLabel(self._entry.input_text, self._body)
        self._input_label.setWordWrap(True)
        self._input_label.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_10')}; "
            f"background: {p['bg_input']}; border: 1px solid {p['line']}; "
            f"border-radius: 4px; padding: 6px;"
        )
        body_layout.addWidget(self._input_label)

        # Output text (read-only QTextEdit for text selection)
        self._output_edit = QTextEdit(self._body)
        self._output_edit.setPlainText(self._entry.output_text)
        self._output_edit.setReadOnly(True)
        self._output_edit.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_10')}; "
            f"background: {p['bg_card']}; border: 1px solid {p['line']}; "
            f"border-radius: 4px; padding: 4px;"
        )
        self._output_edit.setMaximumHeight(150)
        body_layout.addWidget(self._output_edit)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addStretch()

        copy_btn = QPushButton(self._t.t("copy"), self._body)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(
            f"color: {p['text']}; background: {p['accent']}; border: none; "
            f"border-radius: 3px; padding: 3px 10px; font-size: {_fs('fs_9')};"
        )
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._entry.output_text))
        btn_row.addWidget(copy_btn)

        fill_btn = QPushButton(self._t.t("history_fill_output"), self._body)
        fill_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fill_btn.setStyleSheet(
            f"color: {p['text']}; background: {p['accent']}; border: none; "
            f"border-radius: 3px; padding: 3px 10px; font-size: {_fs('fs_9')};"
        )
        fill_btn.clicked.connect(
            lambda: self.fill_requested.emit(self._entry.output_text, self._entry.nochar_text)
        )
        btn_row.addWidget(fill_btn)

        body_layout.addLayout(btn_row)

        self.layout().addWidget(self._body)

    # ── Events ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Only toggle if click is on header area
            header_rect = self._header.geometry()
            if event.position().y() <= header_rect.bottom():
                self.toggle()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        t = self._t
        menu = QMenu(self)
        fill_act = menu.addAction(t.t("history_fill_output"))
        copy_out = menu.addAction(t.t("history_copy_output"))
        copy_in = menu.addAction(t.t("history_copy_input"))
        chosen = menu.exec(event.globalPos())
        if chosen == fill_act:
            self.fill_requested.emit(self._entry.output_text, self._entry.nochar_text)
        elif chosen == copy_out:
            QApplication.clipboard().setText(self._entry.output_text)
        elif chosen == copy_in:
            QApplication.clipboard().setText(self._entry.input_text)

    def enterEvent(self, event):
        p = current_palette()
        self._header.setStyleSheet(
            f"background: {p['hover_bg']}; border-bottom: 1px solid {p['line']};"
        )

    def leaveEvent(self, event):
        p = current_palette()
        self._header.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {p['line']};"
        )

    # ── Theme ──

    def apply_theme(self):
        p = current_palette()
        self._header.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {p['line']};"
        )
        self._toggle_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; border: none;")
        self._ts_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; border: none;")
        if self._model_label:
            self._model_label.setStyleSheet(
                f"color: {p['accent_text']}; font-size: {_fs('fs_9')}; border: none; "
                f"background: {p['accent']}; border-radius: 2px; padding: 0 4px;"
            )
        self._preview_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_9')}; border: none;")
        if self._body and self._input_label:
            self._input_label.setStyleSheet(
                f"color: {p['text']}; font-size: {_fs('fs_10')}; "
                f"background: {p['bg_input']}; border: 1px solid {p['line']}; "
                f"border-radius: 4px; padding: 6px;"
            )
            self._output_edit.setStyleSheet(
                f"color: {p['text']}; font-size: {_fs('fs_10')}; "
                f"background: {p['bg_card']}; border: 1px solid {p['line']}; "
                f"border-radius: 4px; padding: 4px;"
            )


class HistorySidebar(QWidget):
    """Collapsible sidebar panel for generation history, positioned to the right of the workspace card."""

    EXPANDED_WIDTH = 280

    entry_fill_requested = pyqtSignal(str, str)  # output_text, nochar_text
    changed = pyqtSignal()
    width_changed = pyqtSignal(int)

    def __init__(self, translator: Translator, storage: AppStorage, parent=None):
        super().__init__(parent)
        self.setObjectName("HistorySidebar")
        self._t = translator
        self._storage = storage
        self._items: list[_HistorySidebarItem] = []

        p = current_palette()
        self.setStyleSheet(
            f"#HistorySidebar {{ background: {p['bg']}; border-left: 1px solid {p['line_strong']}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        header = QWidget(self)
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 0, 6, 0)
        header_layout.setSpacing(6)

        self._title = QLabel(translator.t("history_panel"), header)
        self._title.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_11')}; font-weight: bold;"
        )
        header_layout.addWidget(self._title)
        header_layout.addStretch()

        self._clear_btn = QPushButton("×", header)
        self._clear_btn.setFixedSize(20, 20)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setToolTip(translator.t("history_clear"))
        self._clear_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; border: none; font-size: {_fs('fs_12')};"
        )
        self._clear_btn.clicked.connect(self._clear_all)
        header_layout.addWidget(self._clear_btn)

        root.addWidget(header)

        # ── Scroll area ──
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent; border: none;")

        self._scroll_content = QWidget()
        self._list_layout = QVBoxLayout(self._scroll_content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._scroll_content)
        root.addWidget(self._scroll, 1)

        # Empty state
        self._empty_label = QLabel(translator.t("history_empty"), self._scroll_content)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_11')};")
        self._list_layout.insertWidget(0, self._empty_label)

        # Initial size
        self.setFixedWidth(self.EXPANDED_WIDTH)

    # ── Public API ──

    def set_entries(self, entries: list[HistoryEntry]):
        """Bulk load entries (newest-first from storage)."""
        for item in self._items:
            self._list_layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._empty_label.setVisible(not entries)
        for e in entries:
            self._add_item(e, save=False)

    def add_entry(self, entry: HistoryEntry):
        """Append a new entry and persist."""
        self._add_item(entry, save=True)

    def _add_item(self, entry: HistoryEntry, save: bool = True):
        self._empty_label.hide()
        item = _HistorySidebarItem(entry, self._t, self._scroll_content)
        item.fill_requested.connect(self.entry_fill_requested.emit)
        self._items.insert(0, item)
        self._list_layout.insertWidget(0, item)
        if save:
            self._storage.append_history(entry)

    def _clear_all(self):
        from .image_manager import _StyledDialog
        if not _StyledDialog.confirm(self, self._t.t("history_clear"),
                                      self._t.t("history_clear_confirm")):
            return
        for item in self._items:
            self._list_layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._storage.clear_history()
        self._empty_label.show()
        self.changed.emit()

    # ── Animation ──

    def animate_show(self):
        """Animate panel expanding from 0 to full width."""
        self.show()
        self.raise_()
        self._animate_width(0, self.EXPANDED_WIDTH)

    def animate_hide(self, on_finish=None):
        """Animate panel collapsing to 0 width, then hide."""
        def _done():
            self.hide()
            self.width_changed.emit(0)
            if on_finish:
                on_finish()
        self._animate_width(self.EXPANDED_WIDTH, 0, on_finish=_done)

    def _animate_width(self, start: int, end: int, on_finish=None):
        anim = QPropertyAnimation(self, b"maximumWidth", self)
        anim.setDuration(200)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumWidth(min(start, end))

        def _on_done():
            self.setMinimumWidth(end)
            self.setMaximumWidth(end)
            self.width_changed.emit(end)
            if on_finish:
                on_finish()

        anim.finished.connect(_on_done)
        anim.valueChanged.connect(lambda: self.width_changed.emit(self.width()))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    # ── Theme ──

    def apply_theme(self):
        p = current_palette()
        self.setStyleSheet(
            f"#HistorySidebar {{ background: {p['bg']}; border-left: 1px solid {p['line_strong']}; }}"
        )
        self._title.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_11')}; font-weight: bold;"
        )
        self._clear_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; border: none; font-size: {_fs('fs_12')};"
        )
        self._empty_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_11')};")
        for item in self._items:
            item.apply_theme()

    def retranslate_ui(self):
        self._title.setText(self._t.t("history_panel"))
        self._clear_btn.setToolTip(self._t.t("history_clear"))
