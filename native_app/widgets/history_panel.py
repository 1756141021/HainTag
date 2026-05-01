"""History Panel — browsable list of past generations."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..models import HistoryEntry
from ..storage import AppStorage
from ..theme import _fs, current_palette
from ..ui_tokens import _dp
from .text_context_menu import apply_app_menu_style


class _HistoryItem(QWidget):
    """A single history entry row."""

    clicked = pyqtSignal(object)  # emits HistoryEntry
    fill_requested = pyqtSignal(str, str)
    restore_requested = pyqtSignal(object)

    def __init__(self, entry: HistoryEntry, translator: Translator, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._t = translator
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        p = current_palette()
        self.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {p['line']};"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_dp(8), _dp(6), _dp(8), _dp(6))
        layout.setSpacing(2)

        # Top row: timestamp + model
        top = QHBoxLayout()
        top.setSpacing(_dp(8))
        self._ts_label = QLabel(entry.timestamp[:16].replace("T", "  "), self)
        self._ts_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; border: none;")
        top.addWidget(self._ts_label)
        self._model_label = None
        if entry.model:
            self._model_label = QLabel(entry.model, self)
            self._model_label.setStyleSheet(
                f"color: {p['accent_text']}; font-size: {_fs('fs_9')}; border: none; "
                f"background: {p['accent']}; border-radius: 2px; padding: 0 4px;"
            )
            top.addWidget(self._model_label)
        top.addStretch()
        layout.addLayout(top)

        # Input preview
        input_preview = entry.input_text[:80].replace("\n", " ")
        if len(entry.input_text) > 80:
            input_preview += "..."
        self._in_label = QLabel(input_preview, self)
        self._in_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_10')}; border: none;")
        self._in_label.setWordWrap(True)
        layout.addWidget(self._in_label)

        # Output preview
        output_preview = entry.output_text[:80].replace("\n", " ")
        if len(entry.output_text) > 80:
            output_preview += "..."
        self._out_label = QLabel(output_preview, self)
        self._out_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_10')}; border: none;")
        self._out_label.setWordWrap(True)
        layout.addWidget(self._out_label)

        self.setFixedHeight(_dp(68))

    def apply_theme(self):
        p = current_palette()
        self.setStyleSheet(f"background: transparent; border-bottom: 1px solid {p['line']};")
        self._ts_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; border: none;")
        if self._model_label:
            self._model_label.setStyleSheet(
                f"color: {p['accent_text']}; font-size: {_fs('fs_9')}; border: none; "
                f"background: {p['accent']}; border-radius: 2px; padding: 0 4px;"
            )
        self._in_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_10')}; border: none;")
        self._out_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_10')}; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._entry)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        t = self._t
        menu = QMenu(self)
        apply_app_menu_style(menu)
        fill_act = menu.addAction(t.t("history_fill_output"))
        restore_act = menu.addAction(t.t("history_restore_workbench"))
        menu.addSeparator()
        copy_out = menu.addAction(t.t("history_copy_output"))
        copy_in = menu.addAction(t.t("history_copy_input"))
        chosen = menu.exec(event.globalPos())
        if chosen == fill_act:
            self.fill_requested.emit(self._entry.output_text, self._entry.nochar_text)
        elif chosen == restore_act:
            self.restore_requested.emit(self._entry)
        elif chosen == copy_out:
            QApplication.clipboard().setText(self._entry.output_text)
        elif chosen == copy_in:
            QApplication.clipboard().setText(self._entry.input_text)

    def enterEvent(self, event):
        p = current_palette()
        self.setStyleSheet(
            f"background: {p['hover_bg']}; border-bottom: 1px solid {p['line']};"
        )

    def leaveEvent(self, event):
        p = current_palette()
        self.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {p['line']};"
        )


class HistoryPanel(QWidget):
    """Scrollable list of past generations with click-to-reuse."""

    entry_selected = pyqtSignal(str)  # output_text
    entry_fill_requested = pyqtSignal(str, str)
    entry_restore_requested = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, translator: Translator, storage: AppStorage, parent=None):
        super().__init__(parent)
        self._t = translator
        self._storage = storage
        self._items: list[_HistoryItem] = []

        p = current_palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(_dp(4), _dp(4), _dp(4), _dp(4))
        root.setSpacing(_dp(4))

        # Header
        header = QHBoxLayout()
        header.setSpacing(_dp(6))
        self._title = QLabel(translator.t("history_panel"), self)
        self._title.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_11')}; font-weight: bold; letter-spacing: 1px;"
        )
        title = self._title
        header.addWidget(title)
        header.addStretch()
        self._clear_btn = QPushButton("×", self)
        self._clear_btn.setFixedSize(_dp(20), _dp(20))
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setToolTip(translator.t("history_clear"))
        self._clear_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; border: none; font-size: {_fs('fs_12')};"
        )
        self._clear_btn.clicked.connect(self._clear_all)
        header.addWidget(self._clear_btn)
        root.addLayout(header)

        # Scroll area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._scroll_content = QWidget()
        self._list_layout = QVBoxLayout(self._scroll_content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        scroll.setWidget(self._scroll_content)
        root.addWidget(scroll, 1)

        # Empty state
        self._empty_label = QLabel(translator.t("history_empty"), self._scroll_content)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_11')};")
        self._list_layout.insertWidget(0, self._empty_label)

    def set_entries(self, entries: list[HistoryEntry]):
        for item in list(self._items):
            self._list_layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._empty_label.setVisible(not entries)
        for e in entries:
            self._add_item(e, save=False)

    def add_entry(self, entry: HistoryEntry):
        self._add_item(entry, save=True)

    def _add_item(self, entry: HistoryEntry, save: bool = True):
        self._empty_label.hide()
        item = _HistoryItem(entry, self._t, self._scroll_content)
        item.clicked.connect(lambda e: self.entry_selected.emit(e.output_text))
        item.fill_requested.connect(self.entry_fill_requested.emit)
        item.restore_requested.connect(self.entry_restore_requested.emit)
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

    def apply_theme(self):
        p = current_palette()
        self._title.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_11')}; font-weight: bold; letter-spacing: 1px;"
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
        self._empty_label.setText(self._t.t("history_empty"))
