"""History Sidebar — grouped generation history beside the main workbench."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PyQt6.QtCore import QEasingCurve, Qt, QPropertyAnimation, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
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
from ..ui_tokens import _dp
from .text_context_menu import apply_app_menu_style


def _entry_datetime(entry: HistoryEntry) -> datetime | None:
    try:
        return datetime.fromisoformat(entry.timestamp)
    except ValueError:
        return None


def _group_label(entry: HistoryEntry, translator: Translator) -> str:
    dt = _entry_datetime(entry)
    if dt is None:
        return entry.timestamp[:10] or translator.t("history_group_unknown")
    today = date.today()
    stamp_date = dt.date()
    if stamp_date == today:
        return translator.t("history_group_today")
    if stamp_date == today - timedelta(days=1):
        return translator.t("history_group_yesterday")
    return stamp_date.isoformat()


class _HistoryTextBlock(QWidget):
    def __init__(self, title: str, text: str, copy_label: str, parent=None):
        super().__init__(parent)
        self._text = text
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(_dp(4))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(_dp(6))
        self._title = QLabel(title, self)
        header.addWidget(self._title)
        header.addStretch()
        self._copy_btn = QPushButton(copy_label, self)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._text))
        header.addWidget(self._copy_btn)
        root.addLayout(header)

        self._editor = QTextEdit(self)
        self._editor.setReadOnly(True)
        self._editor.setPlainText(text)
        self._editor.setMinimumHeight(_dp(72))
        self._editor.setMaximumHeight(_dp(120))
        root.addWidget(self._editor)
        self.apply_theme()

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_copy_label(self, text: str) -> None:
        self._copy_btn.setText(text)

    def apply_theme(self) -> None:
        p = current_palette()
        self._title.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; font-weight: bold;"
        )
        self._copy_btn.setStyleSheet(
            f"color: {p['text']}; background: {p['accent']}; border: none; "
            f"border-radius: {_dp(3)}px; padding: {_dp(3)}px {_dp(10)}px; font-size: {_fs('fs_9')};"
        )
        self._editor.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_10')}; background: {p['bg_card']}; "
            f"border: 1px solid {p['line']}; border-radius: {_dp(4)}px; padding: {_dp(4)}px;"
        )


class _HistorySidebarItem(QWidget):
    output_selected = pyqtSignal(str)
    fill_requested = pyqtSignal(str, str)
    restore_requested = pyqtSignal(object)

    def __init__(self, entry: HistoryEntry, translator: Translator, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._t = translator
        self._collapsed = True
        self._body: QWidget | None = None
        self._input_block: _HistoryTextBlock | None = None
        self._full_block: _HistoryTextBlock | None = None
        self._nochar_block: _HistoryTextBlock | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = QWidget(self)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setFixedHeight(_dp(46))
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(_dp(8), _dp(4), _dp(8), _dp(4))
        header_layout.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(_dp(6))
        self._toggle_label = QLabel("▸", self._header)
        self._toggle_label.setFixedWidth(_dp(12))
        top_row.addWidget(self._toggle_label)

        stamp = entry.timestamp[:16].replace("T", "  ")
        self._ts_label = QLabel(stamp, self._header)
        top_row.addWidget(self._ts_label)

        self._model_label = QLabel(entry.model, self._header)
        self._model_label.setVisible(bool(entry.model))
        top_row.addWidget(self._model_label)
        top_row.addStretch()
        header_layout.addLayout(top_row)

        preview = entry.input_text.replace("\n", " ").strip()
        if len(preview) > 60:
            preview = preview[:60] + "…"
        self._preview_label = QLabel(preview, self._header)
        header_layout.addWidget(self._preview_label)
        root.addWidget(self._header)

        self.setFixedHeight(_dp(46))
        self.apply_theme()

    def _ensure_body(self) -> None:
        if self._body is not None:
            return
        self._body = QWidget(self)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(_dp(8), _dp(4), _dp(8), _dp(8))
        body_layout.setSpacing(_dp(6))

        copy_label = self._t.t("copy")
        self._input_block = _HistoryTextBlock(self._t.t("history_input"), self._entry.input_text, copy_label, self._body)
        body_layout.addWidget(self._input_block)

        self._full_block = _HistoryTextBlock(self._t.t("full_tags"), self._entry.output_text, copy_label, self._body)
        body_layout.addWidget(self._full_block)

        if self._entry.nochar_text.strip():
            self._nochar_block = _HistoryTextBlock(self._t.t("nochar_tags"), self._entry.nochar_text, copy_label, self._body)
            body_layout.addWidget(self._nochar_block)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(_dp(6))
        action_row.addStretch()
        self._fill_btn = QPushButton(self._t.t("history_fill_output"), self._body)
        self._fill_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fill_btn.clicked.connect(
            lambda: self.fill_requested.emit(self._entry.output_text, self._entry.nochar_text)
        )
        action_row.addWidget(self._fill_btn)
        self._restore_btn = QPushButton(self._t.t("history_restore_workbench"), self._body)
        self._restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restore_btn.clicked.connect(lambda: self.restore_requested.emit(self._entry))
        action_row.addWidget(self._restore_btn)
        body_layout.addLayout(action_row)

        self.layout().addWidget(self._body)
        self.apply_theme()

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        if not self._collapsed:
            self._ensure_body()
            self._body.show()
            self._toggle_label.setText("▾")
            self.setFixedHeight(self._header.height() + self._body.sizeHint().height())
        else:
            if self._body is not None:
                self._body.hide()
            self._toggle_label.setText("▸")
            self.setFixedHeight(_dp(46))
        self.updateGeometry()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        apply_app_menu_style(menu)
        fill_act = menu.addAction(self._t.t("history_fill_output"))
        restore_act = menu.addAction(self._t.t("history_restore_workbench"))
        menu.addSeparator()
        copy_input = menu.addAction(self._t.t("history_copy_input"))
        copy_full = menu.addAction(self._t.t("history_copy_output"))
        copy_nochar = None
        if self._entry.nochar_text.strip():
            copy_nochar = menu.addAction(self._t.t("history_copy_nochar"))
        chosen = menu.exec(event.globalPos())
        if chosen == fill_act:
            self.fill_requested.emit(self._entry.output_text, self._entry.nochar_text)
        elif chosen == restore_act:
            self.restore_requested.emit(self._entry)
        elif chosen == copy_input:
            QApplication.clipboard().setText(self._entry.input_text)
        elif chosen == copy_full:
            QApplication.clipboard().setText(self._entry.output_text)
        elif copy_nochar is not None and chosen == copy_nochar:
            QApplication.clipboard().setText(self._entry.nochar_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= self._header.height():
            if event.position().x() <= _dp(28):
                self.toggle()
                return
            self.output_selected.emit(self._entry.output_text)
            self.restore_requested.emit(self._entry)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        p = current_palette()
        self._header.setStyleSheet(f"background: {p['hover_bg']}; border-bottom: 1px solid {p['line']};")
        super().enterEvent(event)

    def leaveEvent(self, event):
        p = current_palette()
        self._header.setStyleSheet(f"background: transparent; border-bottom: 1px solid {p['line']};")
        super().leaveEvent(event)

    def retranslate_ui(self) -> None:
        if self._input_block is not None:
            self._input_block.set_title(self._t.t("history_input"))
            self._input_block.set_copy_label(self._t.t("copy"))
        if self._full_block is not None:
            self._full_block.set_title(self._t.t("full_tags"))
            self._full_block.set_copy_label(self._t.t("copy"))
        if self._nochar_block is not None:
            self._nochar_block.set_title(self._t.t("nochar_tags"))
            self._nochar_block.set_copy_label(self._t.t("copy"))
        if hasattr(self, "_fill_btn"):
            self._fill_btn.setText(self._t.t("history_fill_output"))
        if hasattr(self, "_restore_btn"):
            self._restore_btn.setText(self._t.t("history_restore_workbench"))

    def apply_theme(self) -> None:
        p = current_palette()
        self._header.setStyleSheet(f"background: transparent; border-bottom: 1px solid {p['line']};")
        self._toggle_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')};")
        self._ts_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        self._model_label.setStyleSheet(
            f"color: {p['accent_text']}; font-size: {_fs('fs_9')}; background: {p['accent']}; "
            f"border-radius: {_dp(2)}px; padding: 0 {_dp(4)}px;"
        )
        self._preview_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_9')};")
        if self._input_block is not None:
            self._input_block.apply_theme()
        if self._full_block is not None:
            self._full_block.apply_theme()
        if self._nochar_block is not None:
            self._nochar_block.apply_theme()
        if hasattr(self, "_fill_btn"):
            self._fill_btn.setStyleSheet(
                f"color: {p['text']}; background: {p['accent']}; border: none; "
                f"border-radius: {_dp(3)}px; padding: {_dp(3)}px {_dp(10)}px; font-size: {_fs('fs_9')};"
            )
        if hasattr(self, "_restore_btn"):
            self._restore_btn.setStyleSheet(
                f"color: {p['text_dim']}; background: {p['bg_surface']}; border: 1px solid {p['line']}; "
                f"border-radius: {_dp(3)}px; padding: {_dp(3)}px {_dp(10)}px; font-size: {_fs('fs_9')};"
            )


class HistorySidebar(QWidget):
    EXPANDED_WIDTH = 320

    entry_selected = pyqtSignal(str)
    entry_fill_requested = pyqtSignal(str, str)
    entry_restore_requested = pyqtSignal(object)
    changed = pyqtSignal()
    width_changed = pyqtSignal(int)
    close_requested = pyqtSignal()

    def __init__(self, translator: Translator, storage: AppStorage, parent=None):
        super().__init__(parent)
        self.setObjectName("HistorySidebar")
        self._t = translator
        self._storage = storage
        self._retention_days = 30
        self._entries: list[HistoryEntry] = []
        self._items: list[_HistorySidebarItem] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget(self)
        header.setFixedHeight(_dp(36))
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(_dp(10), 0, _dp(6), 0)
        header_layout.setSpacing(_dp(6))
        self._title = QLabel(header)
        header_layout.addWidget(self._title)
        header_layout.addStretch()
        self._clear_btn = QPushButton("⌫", header)
        self._clear_btn.setFixedSize(_dp(20), _dp(20))
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_all)
        header_layout.addWidget(self._clear_btn)
        self._close_btn = QPushButton("×", header)
        self._close_btn.setFixedSize(_dp(20), _dp(20))
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self._close_btn)
        root.addWidget(header)

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

        self._empty_label = QLabel(self._scroll_content)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.insertWidget(0, self._empty_label)

        self.setFixedWidth(_dp(self.EXPANDED_WIDTH))
        self.retranslate_ui()
        self.apply_theme()

    def set_retention_days(self, retention_days: int) -> None:
        self._retention_days = max(0, int(retention_days))

    def _sorted_entries(self, entries: list[HistoryEntry]) -> list[HistoryEntry]:
        return sorted(
            entries,
            key=lambda entry: _entry_datetime(entry) or datetime.min,
            reverse=True,
        )

    def set_entries(self, entries: list[HistoryEntry]):
        self._entries = self._sorted_entries(entries)
        self._rebuild()

    def add_entry(self, entry: HistoryEntry):
        self._entries.insert(0, entry)
        self._entries = self._sorted_entries(self._entries)
        self._storage.append_history(entry, retention_days=self._retention_days)
        self._entries = self._storage.load_history(retention_days=self._retention_days)
        self._rebuild()
        self.changed.emit()

    def _clear_layout_items(self) -> None:
        while self._list_layout.count() > 2:
            item = self._list_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._items.clear()

    def _rebuild(self) -> None:
        self._clear_layout_items()
        self._empty_label.setVisible(not self._entries)
        if not self._entries:
            return

        current_group = None
        for entry in self._entries:
            group_label = _group_label(entry, self._t)
            if group_label != current_group:
                current_group = group_label
                header = QLabel(group_label, self._scroll_content)
                header.setObjectName("HistoryGroupHeader")
                self._list_layout.insertWidget(self._list_layout.count() - 1, header)
            item = _HistorySidebarItem(entry, self._t, self._scroll_content)
            item.output_selected.connect(self.entry_selected.emit)
            item.fill_requested.connect(self.entry_fill_requested.emit)
            item.restore_requested.connect(self.entry_restore_requested.emit)
            self._items.append(item)
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)
        self.apply_theme()

    def _clear_all(self):
        from .image_manager import _StyledDialog
        if not _StyledDialog.confirm(self, self._t.t("history_clear"), self._t.t("history_clear_confirm")):
            return
        self._entries.clear()
        self._storage.clear_history()
        self._rebuild()
        self.changed.emit()

    def animate_show(self):
        self.show()
        self.raise_()
        self._animate_width(0, _dp(self.EXPANDED_WIDTH))

    def animate_hide(self, on_finish=None):
        def _done():
            self.hide()
            self.width_changed.emit(0)
            if on_finish is not None:
                on_finish()

        self._animate_width(_dp(self.EXPANDED_WIDTH), 0, on_finish=_done)

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
            if on_finish is not None:
                on_finish()

        anim.valueChanged.connect(lambda: self.width_changed.emit(self.width()))
        anim.finished.connect(_on_done)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def retranslate_ui(self):
        self._title.setText(self._t.t("history_panel"))
        self._clear_btn.setToolTip(self._t.t("history_clear"))
        self._close_btn.setToolTip(self._t.t("close_history"))
        self._empty_label.setText(self._t.t("history_empty"))
        for item in self._items:
            item.retranslate_ui()
        self._rebuild()

    def apply_theme(self):
        p = current_palette()
        self.setFixedWidth(_dp(self.EXPANDED_WIDTH))
        self._clear_btn.setFixedSize(_dp(20), _dp(20))
        self._close_btn.setFixedSize(_dp(20), _dp(20))
        self.setStyleSheet(
            f"#HistorySidebar {{ background: {p['bg']}; border-left: 1px solid {p['line_strong']}; }} "
            f"QLabel#HistoryGroupHeader {{ color: {p['text_dim']}; font-size: {_fs('fs_9')}; "
            f"font-weight: bold; padding: {_dp(8)}px {_dp(10)}px {_dp(4)}px {_dp(10)}px; }}"
        )
        self._title.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_11')}; font-weight: bold;"
        )
        self._clear_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; border: none; font-size: {_fs('fs_12')};"
        )
        self._close_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; border: none; font-size: {_fs('fs_12')};"
        )
        self._empty_label.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_11')};"
        )
        for item in self._items:
            item.apply_theme()
