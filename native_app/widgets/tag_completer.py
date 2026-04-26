from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QColor, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..tag_dictionary import TagDictionary, TagInfo
from ..theme import _fs, is_theme_light, DARK_PALETTE, LIGHT_PALETTE

# Danbooru category colors (dark theme / light theme)
_CATEGORY_COLORS: dict[int, tuple[str, str]] = {
    0: ("#6699FF", "#0055CC"),   # general — blue
    1: ("#CC4444", "#CC2222"),   # artist — red
    3: ("#AA44AA", "#882288"),   # copyright — purple
    4: ("#44AA44", "#228822"),   # character — green
    5: ("#FF8800", "#CC6600"),   # meta — orange
}


class TagCompleterPopup(QWidget):
    """Popup showing tag autocomplete suggestions below the text cursor.

    Appears when user types 2+ characters after a comma (or at line start).
    Keyboard: ↑↓ navigate, Enter/Tab accept, Escape dismiss.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._list = QListWidget(self)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

        self._results: list[TagInfo] = []
        self._target_edit: QTextEdit | None = None
        self._token_start: int = 0

    def show_suggestions(self, results: list[TagInfo], edit: QTextEdit, token_start: int) -> None:
        """Display suggestions below the cursor in *edit*."""
        if not results:
            self.hide()
            return

        self._results = results
        self._target_edit = edit
        self._token_start = token_start

        light = is_theme_light()
        pal = LIGHT_PALETTE if light else DARK_PALETTE
        self._list.setStyleSheet(
            f"QListWidget {{ background: {pal['bg_surface']}; border: 1px solid {pal['line_strong']}; "
            f"border-radius: 4px; padding: 2px; }}"
            f"QListWidget::item {{ padding: 3px 6px; border-radius: 3px; }}"
            f"QListWidget::item:selected {{ background: {pal['accent']}; }}"
        )

        self._list.clear()
        for info in results:
            cat_dark, cat_light = _CATEGORY_COLORS.get(info.category_id, ("#6699FF", "#0055CC"))
            cat_color = cat_light if light else cat_dark

            item = QListWidgetItem()
            widget = QWidget()
            row = QHBoxLayout(widget)
            row.setContentsMargins(4, 1, 4, 1)
            row.setSpacing(8)

            name_label = QLabel(info.name.replace("_", " "), widget)
            name_label.setStyleSheet(f"color: {cat_color}; font-weight: bold; font-size: {_fs('fs_12')};")
            row.addWidget(name_label)

            count_label = QLabel(f"{info.count:,}", widget)
            count_label.setStyleSheet(f"color: {pal['text_dim']}; font-size: {_fs('fs_11')};")
            row.addWidget(count_label)

            if info.translation:
                trans_label = QLabel(info.translation, widget)
                trans_label.setStyleSheet(f"color: {pal['text_muted']}; font-size: {_fs('fs_11')};")
                row.addWidget(trans_label)

            row.addStretch()

            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, info.name)
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

        self._list.setCurrentRow(0)

        # Size and position
        row_h = max(24, self._list.sizeHintForRow(0) + 4) if self._list.count() else 24
        height = min(row_h * len(results) + 8, 320)
        width = max(300, edit.width())
        self.resize(width, height)

        # Position below cursor
        cursor = edit.textCursor()
        cursor_rect = edit.cursorRect(cursor)
        global_pos = edit.mapToGlobal(QPoint(cursor_rect.x(), cursor_rect.bottom() + 4))
        self.move(global_pos)
        self.show()

    def apply_theme(self) -> None:
        if self.isVisible() and self._target_edit is not None:
            self.show_suggestions(self._results, self._target_edit, self._token_start)

    def accept_current(self) -> None:
        """Insert the currently selected tag into the target edit."""
        item = self._list.currentItem()
        if item is None or self._target_edit is None:
            self.hide()
            return
        tag_name = item.data(Qt.ItemDataRole.UserRole)
        self._insert_tag(tag_name)
        self.hide()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        tag_name = item.data(Qt.ItemDataRole.UserRole)
        if tag_name and self._target_edit:
            self._insert_tag(tag_name)
        self.hide()

    def _insert_tag(self, tag_name: str) -> None:
        edit = self._target_edit
        if edit is None:
            return
        cursor = edit.textCursor()
        # Select the partial token and replace with the full tag
        cursor.setPosition(self._token_start)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        # Only select up to the current cursor position
        current_pos = edit.textCursor().position()
        cursor.setPosition(self._token_start)
        cursor.setPosition(current_pos, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(tag_name + ", ")
        edit.setTextCursor(cursor)

    def move_selection(self, delta: int) -> None:
        current = self._list.currentRow()
        new_row = max(0, min(self._list.count() - 1, current + delta))
        self._list.setCurrentRow(new_row)


def install_completer(edit: QTextEdit, dictionary: TagDictionary, min_chars: int = 2) -> TagCompleterPopup:
    """Install tag autocomplete on a QTextEdit.

    Returns the popup widget (caller should keep a reference).
    """
    popup = TagCompleterPopup(edit.window())
    _timer = QTimer()
    _timer.setSingleShot(True)
    _timer.setInterval(150)  # debounce

    def _on_text_changed():
        _timer.start()

    def _do_complete():
        if not edit.hasFocus():
            popup.hide()
            return

        cursor = edit.textCursor()
        pos = cursor.position()
        text = edit.toPlainText()

        # Find the start of the current token (after last comma or start of text)
        token_start = text.rfind(",", 0, pos)
        if token_start == -1:
            token_start = 0
        else:
            token_start += 1  # skip the comma

        token = text[token_start:pos].strip()

        if len(token) < min_chars:
            popup.hide()
            return

        results = dictionary.search_prefix(token, limit=12)
        if results:
            popup.show_suggestions(results, edit, token_start + (len(text[token_start:pos]) - len(text[token_start:pos].lstrip())))
        else:
            popup.hide()

    _suppress_until = [0]  # timestamp to suppress completions after accept

    def _do_complete_guarded():
        import time
        if time.monotonic() < _suppress_until[0]:
            return
        _do_complete()

    _timer.timeout.connect(_do_complete_guarded)
    edit.textChanged.connect(_on_text_changed)

    # Intercept key events on the edit
    original_key_press = edit.keyPressEvent

    def _key_press(event: QKeyEvent):
        if popup.isVisible():
            if event.key() == Qt.Key.Key_Down:
                popup.move_selection(1)
                return
            if event.key() == Qt.Key.Key_Up:
                popup.move_selection(-1)
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                import time
                popup.accept_current()
                _suppress_until[0] = time.monotonic() + 0.3
                edit.setFocus()
                return
            if event.key() == Qt.Key.Key_Escape:
                popup.hide()
                edit.setFocus()
                return
        original_key_press(event)

    edit.keyPressEvent = _key_press

    # Hide popup when edit loses focus
    original_focus_out = edit.focusOutEvent

    def _focus_out(event):
        # Delay hide to allow popup clicks to register
        QTimer.singleShot(200, lambda: popup.hide() if not edit.hasFocus() else None)
        original_focus_out(event)

    edit.focusOutEvent = _focus_out

    # Also hide when window is deactivated
    def _check_active():
        try:
            from PyQt6 import sip
            if sip.isdeleted(edit):
                _active_timer.stop()
                return
            if not edit.isVisible() or not edit.window().isActiveWindow():
                popup.hide()
        except RuntimeError:
            _active_timer.stop()

    # Periodic check (lightweight)
    _active_timer = QTimer()
    _active_timer.setInterval(500)
    _active_timer.timeout.connect(_check_active)
    _active_timer.start()
    edit._tag_completer_active_timer = _active_timer

    # Keep references alive
    edit._tag_completer_popup = popup
    edit._tag_completer_timer = _timer

    return popup
