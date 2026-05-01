from __future__ import annotations

from html import escape

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..tag_dictionary import TagDictionary, TagInfo
from ..theme import _fs, current_palette
from ..ui_tokens import _dp


_SEMANTIC_COLORS: dict[str, str] = {
    "character": "#93b8e8",
    "appearance": "#d8a8c5",
    "action": "#e6c279",
    "scene": "#8fc9a4",
    "style": "#b9a3e0",
    "camera": "#a8a8a8",
    "emotion": "#e89c9c",
}


def _tr(widget: QWidget | None, key: str, fallback: str) -> str:
    window = widget.window() if widget is not None else None
    translator = getattr(window, "_translator", None)
    if translator is not None:
        value = translator.t(key)
        if value and value != key:
            return value
    return fallback


def _normalize(text: str) -> str:
    return text.strip().lower().replace(" ", "_")


def _format_posts(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.0f}k"
    return str(max(0, count))


def _semantic_category(info: TagInfo) -> str:
    hay = f"{info.name} {info.translation} {info.group} {info.subgroup}".lower()
    if info.category_id == 4:
        return "character"
    if any(s in hay for s in ("smile", "blush", "cry", "tear", "angry", "happy", "sad", "emotion", "expression", "表情", "情绪")):
        return "emotion"
    if any(s in hay for s in ("looking", "sitting", "standing", "lying", "holding", "walking", "running", "pose", "action", "hand", "arm", "leg", "动作", "姿势")):
        return "action"
    if any(s in hay for s in ("background", "indoors", "outdoors", "room", "school", "city", "forest", "sky", "water", "scene", "场景", "背景")):
        return "scene"
    if any(s in hay for s in ("view", "focus", "pov", "from_", "close-up", "camera", "composition", "构图", "视角")):
        return "camera"
    if info.category_id in {1, 3, 5} or any(s in hay for s in ("masterpiece", "quality", "style", "lighting", "artist", "meta", "风格", "质量", "光")):
        return "style"
    return "appearance"


def _highlight_match(text: str, query: str) -> str:
    p = current_palette()
    display = text.replace("_", " ")
    q = query.replace("_", " ").strip()
    if not q:
        return escape(display)
    start = display.lower().find(q.lower())
    if start < 0:
        return escape(display)
    end = start + len(q)
    return (
        escape(display[:start])
        + f'<span style="color:{p["accent_text"]};">'
        + escape(display[start:end])
        + "</span>"
        + escape(display[end:])
    )


class _SectionLabel(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(4))
        layout.setSpacing(_dp(6))
        label = QLabel(text, self)
        label.setObjectName("AcSectionLabel")
        line = QFrame(self)
        line.setObjectName("AcSectionLine")
        line.setFixedHeight(1)
        layout.addWidget(label)
        layout.addWidget(line, 1)


class _SuggestionRow(QFrame):
    picked = pyqtSignal(object)

    def __init__(self, info: TagInfo, query: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info
        self._active = False
        self.setObjectName("AcRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_dp(10), _dp(7), _dp(10), _dp(7))
        layout.setSpacing(_dp(10))

        dot = QLabel(self)
        dot.setObjectName("AcCatDot")
        dot.setFixedSize(_dp(8), _dp(8))
        color = _SEMANTIC_COLORS.get(_semantic_category(info), _SEMANTIC_COLORS["appearance"])
        dot.setStyleSheet(f"QLabel#AcCatDot {{ background: {color}; border-radius: {_dp(4)}px; }}")
        layout.addWidget(dot)

        name_wrap = QWidget(self)
        name_layout = QHBoxLayout(name_wrap)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(_dp(6))
        self._name = QLabel(name_wrap)
        self._name.setObjectName("AcName")
        self._name.setTextFormat(Qt.TextFormat.RichText)
        self._name.setText(_highlight_match(info.name, query))
        name_layout.addWidget(self._name)

        alias_text = self._alias_text(info)
        if alias_text:
            alias = QLabel(alias_text, name_wrap)
            alias.setObjectName("AcAlias")
            name_layout.addWidget(alias)
        name_layout.addStretch(1)
        layout.addWidget(name_wrap, 1)

        self._meta = QLabel(
            _tr(self, "tag_posts_count", "{count} posts").format(count=_format_posts(info.count)),
            self,
        )
        self._meta.setObjectName("AcMeta")
        layout.addWidget(self._meta)

        self._shortcut = QLabel("↵", self)
        self._shortcut.setObjectName("AcShortcut")
        layout.addWidget(self._shortcut)
        self.apply_style()

    @staticmethod
    def _alias_text(info: TagInfo) -> str:
        if info.translation:
            return info.translation
        if info.aliases:
            return "→ " + info.aliases[0].replace("_", " ")
        return ""

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setProperty("active", active)
        self.apply_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.info)
            event.accept()
            return
        super().mousePressEvent(event)

    def apply_style(self) -> None:
        p = current_palette()
        if self._active:
            row_style = f"background: {p['accent_sub']}; border-left: 2px solid {p['accent_text']};"
            shortcut_bg = p["hover_bg"]
            shortcut_fg = p["text_label"]
            shortcut_border = p["line"]
        else:
            row_style = "background: transparent; border-left: 2px solid transparent;"
            shortcut_bg = "transparent"
            shortcut_fg = "transparent"
            shortcut_border = "transparent"
        self.setStyleSheet(
            "QFrame#AcRow { "
            f"{row_style} border-radius: {_dp(3)}px; }}"
            f"QFrame#AcRow:hover {{ background: {p['hover_bg']}; }}"
            f"QLabel#AcName {{ color: {p['text']}; font-size: {_fs('fs_12')}; }}"
            f"QLabel#AcAlias {{ color: {p['text_label']}; font-size: {_fs('fs_9')}; font-style: italic; }}"
            f"QLabel#AcMeta {{ color: {p['text_label']}; font-size: {_fs('fs_9')}; }}"
            f"QLabel#AcShortcut {{ color: {shortcut_fg}; background: {shortcut_bg}; border: 1px solid {shortcut_border}; "
            f"border-radius: {_dp(2)}px; padding: 1px {_dp(5)}px; font-size: {_fs('fs_8')}; }}"
        )


class TagCompleterPopup(QWidget):
    """HTML-design autocomplete popup for TAG suggestions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("AcFrame")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._drop = QFrame(self)
        self._drop.setObjectName("AcDrop")
        self._rows_layout = QVBoxLayout(self._drop)
        self._rows_layout.setContentsMargins(_dp(4), _dp(4), _dp(4), _dp(4))
        self._rows_layout.setSpacing(0)
        root.addWidget(self._drop)

        self._footer = QFrame(self)
        self._footer.setObjectName("AcFooter")
        footer_layout = QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(_dp(12), _dp(7), _dp(12), _dp(7))
        footer_layout.setSpacing(_dp(14))
        self._move_label = QLabel(self._footer)
        self._accept_label = QLabel(self._footer)
        self._tab_label = QLabel(self._footer)
        self._cancel_label = QLabel(self._footer)
        self._source_label = QLabel(self._footer)
        for label in (self._move_label, self._accept_label, self._tab_label, self._cancel_label, self._source_label):
            label.setTextFormat(Qt.TextFormat.RichText)
        for label in (self._move_label, self._accept_label, self._tab_label, self._cancel_label):
            footer_layout.addWidget(label)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._source_label)
        root.addWidget(self._footer)

        self._results: list[TagInfo] = []
        self._rows: list[_SuggestionRow] = []
        self._target_edit: QTextEdit | None = None
        self._token_start = 0
        self._query = ""
        self._active_index = 0
        self.apply_theme()

    def show_suggestions(self, results: list[TagInfo], edit: QTextEdit, token_start: int, query: str = "") -> None:
        if not results:
            self.hide()
            return
        self._results = results
        self._target_edit = edit
        self._token_start = token_start
        self._query = query
        self._active_index = 0
        self._refresh_footer()
        self._rebuild_rows()
        self._set_active_row(0)

        row_h = 31
        section_count = self._section_count(results, query)
        height = min(row_h * len(results) + section_count * 24 + 40, 360)
        width = min(max(280, edit.width(), _dp(300)), _dp(520))
        self.resize(width, height)

        cursor = edit.textCursor()
        cursor_rect = edit.cursorRect(cursor)
        global_pos = edit.mapToGlobal(QPoint(cursor_rect.x(), cursor_rect.bottom() + _dp(4)))
        self.move(global_pos)
        self.show()
        self.raise_()

    def apply_theme(self) -> None:
        p = current_palette()
        self.setStyleSheet(
            f"QWidget#AcFrame {{ background: {p['bg_menu']}; border: 1px solid {p['line_strong']}; border-radius: {_dp(4)}px; }}"
            f"QFrame#AcDrop {{ background: {p['bg_menu']}; border: none; }}"
            f"QFrame#AcFooter {{ background: {p['bg_menu']}; border-top: 1px solid {p['line']}; }}"
            f"QLabel#AcSectionLabel {{ color: {p['text_label']}; font-size: {_fs('fs_8')}; letter-spacing: 1px; }}"
            f"QFrame#AcSectionLine {{ background: {p['line']}; }}"
        )
        self._refresh_footer()
        for row in self._rows:
            row.apply_style()

    def accept_current(self) -> None:
        if not self._rows or self._target_edit is None:
            self.hide()
            return
        self._insert_tag(self._rows[self._active_index].info.name)
        self.hide()

    def move_selection(self, delta: int) -> None:
        if not self._rows:
            return
        self._set_active_row(max(0, min(len(self._rows) - 1, self._active_index + delta)))

    def _rebuild_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

        groups = self._group_results(self._results, self._query)
        for section_key, items in groups:
            if not items:
                continue
            self._rows_layout.addWidget(_SectionLabel(self._section_text(section_key), self._drop))
            for info in items:
                row = _SuggestionRow(info, self._query, self._drop)
                row.picked.connect(self._pick_info)
                self._rows.append(row)
                self._rows_layout.addWidget(row)
        self._rows_layout.addStretch(1)

    def _set_active_row(self, index: int) -> None:
        self._active_index = index
        for i, row in enumerate(self._rows):
            row.set_active(i == index)

    def _pick_info(self, info: TagInfo) -> None:
        self._insert_tag(info.name)
        self.hide()
        if self._target_edit is not None:
            self._target_edit.setFocus()

    def _insert_tag(self, tag_name: str) -> None:
        edit = self._target_edit
        if edit is None:
            return
        cursor = edit.textCursor()
        current_pos = cursor.position()
        cursor.setPosition(self._token_start)
        cursor.setPosition(current_pos, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(tag_name + ", ")
        edit.setTextCursor(cursor)

    def _refresh_footer(self) -> None:
        p = current_palette()
        def kbd(text: str) -> str:
            return (
                f'<span style="font-size:{_fs("fs_9")};color:{p["text_label"]};background:{p["hover_bg"]};'
                f'border:1px solid {p["line"]};border-radius:{_dp(2)}px;padding:1px {_dp(5)}px;">'
                f"{escape(text)}</span>"
            )

        move = _tr(self._target_edit or self, "ac_move", "移动")
        selected = _tr(self._target_edit or self, "ac_select", "选中")
        accept = _tr(self._target_edit or self, "ac_accept", "接受")
        cancel = _tr(self._target_edit or self, "ac_cancel", "取消")
        source = _tr(self._target_edit or self, "ac_source_danbooru", "来源 · Danbooru wiki")
        style = f'style="color:{p["text_label"]};font-size:{_fs("fs_10")};"'
        self._move_label.setText(f'<span {style}>{kbd("↑")}{kbd("↓")} {escape(move)}</span>')
        self._accept_label.setText(f'<span {style}>{kbd("↵")} {escape(selected)}</span>')
        self._tab_label.setText(f'<span {style}>{kbd("Tab")} {escape(accept)}</span>')
        self._cancel_label.setText(f'<span {style}>{kbd("Esc")} {escape(cancel)}</span>')
        self._source_label.setText(f'<span {style}><i>{escape(source)}</i></span>')

    @staticmethod
    def _group_results(results: list[TagInfo], query: str) -> list[tuple[str, list[TagInfo]]]:
        q = _normalize(query)
        best: list[TagInfo] = []
        related: list[TagInfo] = []
        for info in results:
            if _normalize(info.name).startswith(q):
                best.append(info)
            else:
                related.append(info)
        if not best:
            best, related = related, []
        return [("best", best), ("related", related)]

    @staticmethod
    def _section_count(results: list[TagInfo], query: str) -> int:
        return sum(1 for _, items in TagCompleterPopup._group_results(results, query) if items)

    def _section_text(self, key: str) -> str:
        if key == "best":
            return _tr(self._target_edit or self, "ac_best_match", "最佳匹配")
        return _tr(self._target_edit or self, "ac_related", "相关")


def install_completer(edit: QTextEdit, dictionary: TagDictionary, min_chars: int = 2) -> TagCompleterPopup:
    """Install HTML-style TAG autocomplete on a QTextEdit."""
    popup = TagCompleterPopup(edit.window())
    _timer = QTimer()
    _timer.setSingleShot(True)
    _timer.setInterval(150)

    def _on_text_changed() -> None:
        _timer.start()

    def _do_complete() -> None:
        if not edit.hasFocus():
            popup.hide()
            return

        cursor = edit.textCursor()
        pos = cursor.position()
        text = edit.toPlainText()
        token_start = text.rfind(",", 0, pos)
        token_start = 0 if token_start == -1 else token_start + 1
        raw_token = text[token_start:pos]
        token = raw_token.strip()
        if len(token) < min_chars:
            popup.hide()
            return

        adjusted_start = token_start + (len(raw_token) - len(raw_token.lstrip()))
        results = dictionary.search_prefix(token, limit=12)
        if results:
            popup.show_suggestions(results, edit, adjusted_start, token)
        else:
            popup.hide()

    _suppress_until = [0.0]

    def _do_complete_guarded() -> None:
        import time
        if time.monotonic() < _suppress_until[0]:
            return
        _do_complete()

    _timer.timeout.connect(_do_complete_guarded)
    edit.textChanged.connect(_on_text_changed)

    original_key_press = edit.keyPressEvent

    def _key_press(event: QKeyEvent) -> None:
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

    original_focus_out = edit.focusOutEvent

    def _focus_out(event) -> None:
        QTimer.singleShot(200, lambda: popup.hide() if not edit.hasFocus() else None)
        original_focus_out(event)

    edit.focusOutEvent = _focus_out

    def _check_active() -> None:
        try:
            from PyQt6 import sip
            if sip.isdeleted(edit):
                _active_timer.stop()
                return
            if not edit.isVisible() or not edit.window().isActiveWindow():
                popup.hide()
        except RuntimeError:
            _active_timer.stop()

    _active_timer = QTimer()
    _active_timer.setInterval(500)
    _active_timer.timeout.connect(_check_active)
    _active_timer.start()

    edit._tag_completer_popup = popup
    edit._tag_completer_timer = _timer
    edit._tag_completer_active_timer = _active_timer
    return popup
