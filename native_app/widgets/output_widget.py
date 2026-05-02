from __future__ import annotations

import re
from html import escape
from dataclasses import dataclass, field

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPolygon,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidgetItem,
    QWidget,
)

from ..i18n import Translator
from ..tag_dictionary import TagDictionary
from ..theme import _fs, current_palette, is_theme_light
from ..ui_tokens import _dp
from .text_context_menu import show_text_edit_context_menu

# Regex to parse a single tag's weight: (tag:1.3) or plain tag
_SD_WEIGHT_RE = re.compile(r'\(([^()]+):(\d+\.?\d*)\)')
_CSS_RGBA_RE = re.compile(
    r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)',
    re.IGNORECASE,
)
_WEIGHT_SCRUB_PER_PX = 0.02


def _weight_scrub_step() -> float:
    """Use one scrub scale for text and chip editing, with modifiers for precision."""
    modifiers = QApplication.keyboardModifiers()
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        return _WEIGHT_SCRUB_PER_PX * 2.5
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        return _WEIGHT_SCRUB_PER_PX * 0.25
    return _WEIGHT_SCRUB_PER_PX


def _css_color(value: str, fallback: str = "#ffffff") -> QColor:
    color = QColor(value)
    if color.isValid():
        return color
    m = _CSS_RGBA_RE.fullmatch((value or "").strip())
    if m:
        r, g, b = (int(m.group(i)) for i in range(1, 4))
        a = max(0, min(255, round(float(m.group(4)) * 255)))
        return QColor(r, g, b, a)
    return QColor(fallback)


def _palette_color(name: str, alpha: int | None = None) -> QColor:
    color = _css_color(current_palette().get(name, "#ffffff"))
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def _format_weight(value: float) -> str:
    """Format Stable Diffusion tag weights without losing useful precision."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _category_display_name(translator: Translator, category: str) -> str:
    semantic = _semantic_category(category)
    key = f"tag_category_{semantic}"
    translated = translator.t(key)
    if translated != key:
        return translated
    if translator.get_language().lower().startswith("zh"):
        return _CATEGORY_NAMES_ZH.get(semantic, semantic)
    return semantic

# ── TAG category system ──
# Separator: § = category block, ¦ = tag within block
_CATEGORY_SEPARATOR = '§'
_CATEGORY_TAG_SEP = '¦'
_CATEGORY_BLOCK_RE = re.compile(r'§(\w+)((?:¦[^§¦]+)+)')
_TAG_DELIMITER_RE = re.compile(r'[,\n]')


CATEGORY_COLORS: dict[str, str] = {
    'character':  '#93b8e8',
    'appearance': '#d8a8c5',
    'action':     '#e6c279',
    'scene':      '#8fc9a4',
    'style':      '#b9a3e0',
    'camera':     '#a8a8a8',
    'emotion':    '#e89c9c',
    # Backward-compatible aliases used by older prompts / dictionaries.
    'pose':       '#e6c279',
    'clothing':   '#d8a8c5',
    'expression': '#e89c9c',
    'body':       '#d8a8c5',
    'quality':    '#b9a3e0',
    'lighting':   '#b9a3e0',
    'effect':     '#b9a3e0',
    'nsfw':       '#e89c9c',
    'accessory':  '#d8a8c5',
    'text':       '#a8a8a8',
}

_CATEGORY_NAMES_ZH: dict[str, str] = {
    'character': '角色',
    'scene': '场景',
    'pose': '姿势',
    'clothing': '服饰',
    'expression': '表情',
    'body': '身体',
    'style': '风格',
    'quality': '质量',
    'lighting': '光影',
    'camera': '视角',
    'effect': '效果',
    'nsfw': 'NSFW',
    'action': '动作',
    'accessory': '配件',
    'text': '文字',
}

_SEMANTIC_ALIASES: dict[str, str] = {
    'character': 'character',
    'appearance': 'appearance',
    'clothing': 'appearance',
    'body': 'appearance',
    'accessory': 'appearance',
    'action': 'action',
    'pose': 'action',
    'scene': 'scene',
    'style': 'style',
    'quality': 'style',
    'lighting': 'style',
    'effect': 'style',
    'artist': 'style',
    'meta': 'style',
    'camera': 'camera',
    'composition': 'camera',
    'text': 'camera',
    'emotion': 'emotion',
    'expression': 'emotion',
    'nsfw': 'emotion',
}

_CATEGORY_ID_SEMANTIC: dict[int, str] = {
    0: 'appearance',
    1: 'style',
    3: 'style',
    4: 'character',
    5: 'style',
}

CATEGORY_COLORS_LIGHT: dict[str, str] = {
    'character':  '#4e7caf',
    'appearance': '#a96888',
    'action':     '#a88432',
    'scene':      '#4d8c60',
    'style':      '#8063ad',
    'camera':     '#747474',
    'emotion':    '#ad5f5f',
    'pose':       '#a88432',
    'clothing':   '#a96888',
    'expression': '#ad5f5f',
    'body':       '#a96888',
    'quality':    '#8063ad',
    'lighting':   '#8063ad',
    'effect':     '#8063ad',
    'nsfw':       '#ad5f5f',
    'accessory':  '#a96888',
    'text':       '#747474',
}


def _normalize_tag_name(tag: str) -> str:
    m = _SD_WEIGHT_RE.match(tag.strip())
    name = m.group(1).strip() if m else tag.strip().strip('(){}[] ')
    return name.lower().replace(' ', '_')


def _iter_tag_chunks(text: str):
    start = 0
    for match in _TAG_DELIMITER_RE.finditer(text):
        yield text[start:match.start()], start, match.start()
        start = match.end()
    yield text[start:], start, len(text)


def _semantic_category(category: str) -> str:
    return _SEMANTIC_ALIASES.get((category or '').lower(), (category or 'appearance').lower())


def _tag_semantic_from_dictionary(dictionary: TagDictionary | None, tag: str) -> str:
    if dictionary is None:
        return 'appearance'
    info = dictionary.lookup(tag)
    if info is None:
        return 'appearance'
    hay = f"{info.name} {info.translation} {info.group} {info.subgroup}".lower()
    if any(s in hay for s in ('smile', 'blush', 'cry', 'tear', 'angry', 'happy', 'sad', 'emotion', 'expression', '表情', '情绪')):
        return 'emotion'
    if any(s in hay for s in ('looking', 'sitting', 'standing', 'lying', 'holding', 'walking', 'running', 'pose', 'action', 'hand', 'arm', 'leg', '动作', '姿势')):
        return 'action'
    if any(s in hay for s in ('background', 'indoors', 'outdoors', 'room', 'school', 'city', 'forest', 'sky', 'water', 'scene', '场景', '背景')):
        return 'scene'
    if any(s in hay for s in ('view', 'focus', 'pov', 'from_', 'close-up', 'camera', 'composition', '构图', '视角')):
        return 'camera'
    if any(s in hay for s in ('masterpiece', 'quality', 'style', 'lighting', 'artist', 'meta', '风格', '质量', '光')):
        return 'style'
    if info.category_id in _CATEGORY_ID_SEMANTIC:
        return _CATEGORY_ID_SEMANTIC[info.category_id]
    return 'appearance'


def parse_category_mapping(raw: str) -> dict[str, str]:
    """Parse §category¦tag1¦tag2§category2¦tag3 → {tag: category}."""
    mapping: dict[str, str] = {}
    for m in _CATEGORY_BLOCK_RE.finditer(raw):
        cat = m.group(1).lower()
        tags_part = m.group(2)  # ¦tag1¦tag2
        for chunk in tags_part.split(_CATEGORY_TAG_SEP):
            for tag in chunk.split(','):
                tag = tag.strip()
                if tag:
                    mapping[tag.lower().replace(' ', '_')] = cat
    return mapping


def extract_by_markers(text: str, start_marker: str, end_marker: str) -> str | None:
    """Extract content between start and end markers. Returns None if not found."""
    if not start_marker or not end_marker:
        return None
    s = text.find(start_marker)
    if s < 0:
        return None
    s += len(start_marker)
    e = text.find(end_marker, s)
    if e < 0:
        # No end marker: take everything after start marker
        return text[s:].strip()
    return text[s:e].strip()


def split_tags_and_mapping(text: str) -> tuple[str, dict[str, str]]:
    """Split LLM output into pure tags + category mapping.

    If text contains §, everything from the first § onward is the mapping.
    Returns (clean_tags, category_dict).
    """
    idx = text.find(_CATEGORY_SEPARATOR)
    if idx < 0:
        return text, {}
    clean = text[:idx].rstrip()
    mapping = parse_category_mapping(text[idx:])
    return clean, mapping


class TagCategoryHighlighter(QSyntaxHighlighter):
    """Syntax highlighter that colors tags by their category."""

    def __init__(self, document: QTextDocument, parent=None):
        super().__init__(document)
        self._tag_categories: dict[str, str] = {}

    def set_categories(self, categories: dict[str, str]) -> None:
        self._tag_categories = categories
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        if not self._tag_categories or not text.strip():
            return
        colors = CATEGORY_COLORS_LIGHT if is_theme_light() else CATEGORY_COLORS
        for raw_tag, start, end in _iter_tag_chunks(text):
            stripped = raw_tag.strip()
            # Extract tag name (strip weight syntax)
            m = _SD_WEIGHT_RE.match(stripped)
            name = m.group(1).strip() if m else stripped.strip('(){}[] ')
            norm = name.lower().replace(' ', '_')
            cat = self._tag_categories.get(norm)
            if cat and cat in colors:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(colors[cat]))
                self.setFormat(start, end - start, fmt)


@dataclass
class _TagSpan:
    start: int
    end: int
    name: str
    weight: float
    has_parens: bool
    category: str = ""


class TagTextEdit(QTextEdit):
    """QTextEdit with TAG hover highlight and right-click drag weight editing."""

    tag_hovered = pyqtSignal(str)

    _DRAG_THRESHOLD = 5  # pixels before drag starts

    def __init__(self, translator: Translator | None = None, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_local_context_menu)
        self.setMouseTracking(True)
        self._tags: list[_TagSpan] = []
        self._hovered_tag: _TagSpan | None = None
        self._dictionary: TagDictionary | None = None
        self._tag_categories: dict[str, str] = {}
        self._scrub_tag: _TagSpan | None = None
        self._scrub_origin_x = 0
        self._scrub_origin_weight = 1.0
        # Drag-to-reorder state
        self._drag_candidate: _TagSpan | None = None
        self._drag_start_pos: QPoint | None = None
        self._drag_active = False
        self._drag_target_idx: int = -1
        self.textChanged.connect(self._reparse_tags)
        self._highlighter = TagCategoryHighlighter(self.document(), self)

    def set_dictionary(self, dictionary: TagDictionary) -> None:
        self._dictionary = dictionary

    def set_tag_categories(self, categories: dict[str, str]) -> None:
        """Set tag→category mapping for syntax highlighting."""
        self._tag_categories = categories
        self._highlighter.set_categories(categories)
        self._reparse_tags()

    def _reparse_tags(self) -> None:
        text = self.toPlainText()
        self._tags.clear()
        if not text.strip():
            return
        for raw_tag, start, end in _iter_tag_chunks(text):
            stripped = raw_tag.strip()
            m = _SD_WEIGHT_RE.match(stripped)
            if m:
                name = m.group(1).strip()
                weight = float(m.group(2))
                has_parens = True
            else:
                clean = stripped.strip('(){}[] ')
                name = clean
                weight = 1.0
                has_parens = stripped.startswith('(') and ':' in stripped
            if name:
                norm = name.lower().replace(' ', '_')
                cat = self._tag_categories.get(norm, "")
                self._tags.append(_TagSpan(start, end, name, weight, has_parens, cat))

    def _tag_at_cursor(self, pos: QPoint) -> _TagSpan | None:
        cursor = self.cursorForPosition(pos)
        char_pos = cursor.position()
        for tag in self._tags:
            if tag.start <= char_pos < tag.end:
                return tag
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._scrub_tag is not None:
            self._handle_scrub_move(event)
            return
        # Drag-to-reorder: detect threshold then track
        if self._drag_candidate is not None and self._drag_start_pos is not None:
            if not self._drag_active:
                delta = event.pos() - self._drag_start_pos
                if abs(delta.x()) + abs(delta.y()) >= self._DRAG_THRESHOLD:
                    self._drag_active = True
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            if self._drag_active:
                self._handle_drag_move(event)
                return
        tag = self._tag_at_cursor(event.pos())
        if tag != self._hovered_tag:
            self._clear_highlight()
            self._hovered_tag = tag
            if tag:
                self._apply_highlight(tag)
                self.tag_hovered.emit(tag.name)
                lines = []
                if self._dictionary:
                    tr = self._dictionary.translate(tag.name)
                    if tr:
                        lines.append(tr)
                if tag.category:
                    lines.append(f'[{_CATEGORY_NAMES_ZH.get(tag.category, tag.category)}]')
                tip = '\n'.join(lines) if lines else tag.name
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            tag = self._tag_at_cursor(event.pos())
            if tag:
                self._scrub_tag = tag
                self._scrub_origin_x = event.globalPosition().toPoint().x()
                self._scrub_origin_weight = tag.weight
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton:
            tag = self._tag_at_cursor(event.pos())
            if tag:
                self._drag_candidate = tag
                self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton and self._scrub_tag is not None:
            self._scrub_tag = None
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self.textChanged.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_active and self._drag_candidate is not None:
                self._finish_drag_reorder()
                event.accept()
                return
            self._drag_candidate = None
            self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _handle_scrub_move(self, event: QMouseEvent) -> None:
        if self._scrub_tag is None:
            return
        dx = event.globalPosition().toPoint().x() - self._scrub_origin_x
        delta = dx * _weight_scrub_step()
        new_weight = round(max(0.1, min(2.0, self._scrub_origin_weight + delta)), 2)
        if new_weight == self._scrub_tag.weight:
            return
        self._apply_weight(self._scrub_tag, new_weight)

    def _apply_weight(self, tag: _TagSpan, new_weight: float) -> None:
        text = self.toPlainText()
        old_text = text[tag.start:tag.end]
        stripped = old_text.strip()

        if abs(new_weight - 1.0) < 0.01:
            # Weight is 1.0 → strip to plain tag name
            new_tag_core = tag.name
        else:
            new_tag_core = f'({tag.name}:{_format_weight(new_weight)})'

        # Preserve leading/trailing whitespace from original
        leading = old_text[:len(old_text) - len(old_text.lstrip())]
        trailing = old_text[len(old_text.rstrip()):]
        new_text = leading + new_tag_core + trailing

        cursor = self.textCursor()
        cursor.setPosition(tag.start)
        cursor.setPosition(tag.end, QTextCursor.MoveMode.KeepAnchor)
        self.blockSignals(True)
        cursor.insertText(new_text)
        self.blockSignals(False)

        # Update tag in-place
        length_diff = len(new_text) - (tag.end - tag.start)
        tag.end = tag.start + len(new_text)
        tag.weight = new_weight
        tag.has_parens = abs(new_weight - 1.0) >= 0.01
        # Shift subsequent tags
        for t in self._tags:
            if t.start > tag.start:
                t.start += length_diff
                t.end += length_diff

    # ── Drag-to-reorder ──

    def _handle_drag_move(self, event: QMouseEvent) -> None:
        cursor = self.cursorForPosition(event.pos())
        char_pos = cursor.position()
        # Find insertion index: before which tag should we drop?
        target_idx = len(self._tags)  # default: end
        for i, tag in enumerate(self._tags):
            mid = (tag.start + tag.end) // 2
            if char_pos < mid:
                target_idx = i
                break
        self._drag_target_idx = target_idx
        self._apply_drag_selections()

    def _apply_drag_selections(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        # Highlight the dragged tag (dimmed)
        if self._drag_candidate:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(_palette_color("selection_bg", 40))
            sel.format.setForeground(_palette_color("text_muted"))
            c = self.textCursor()
            c.setPosition(self._drag_candidate.start)
            c.setPosition(self._drag_candidate.end, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            selections.append(sel)
        # Highlight drop target tag (accent border)
        if 0 <= self._drag_target_idx < len(self._tags):
            target = self._tags[self._drag_target_idx]
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(_palette_color("accent", 60))
            c = self.textCursor()
            c.setPosition(target.start)
            c.setPosition(target.end, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            selections.append(sel)
        self.setExtraSelections(selections)

    def _finish_drag_reorder(self) -> None:
        src_tag = self._drag_candidate
        target_idx = self._drag_target_idx
        # Reset state
        self._drag_candidate = None
        self._drag_start_pos = None
        self._drag_active = False
        self._drag_target_idx = -1
        self.setExtraSelections([])
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction
        )
        if src_tag is None or not self._tags:
            return
        # Find source index
        src_idx = -1
        for i, t in enumerate(self._tags):
            if t is src_tag:
                src_idx = i
                break
        if src_idx < 0 or target_idx == src_idx or target_idx == src_idx + 1:
            return  # no-op: dropped at same position
        # Rebuild tag list in new order
        text = self.toPlainText()
        tag_texts = []
        for tag in self._tags:
            tag_texts.append(text[tag.start:tag.end].strip())
        moved = tag_texts.pop(src_idx)
        insert_at = target_idx if target_idx < src_idx else target_idx - 1
        tag_texts.insert(insert_at, moved)
        new_text = ', '.join(tag_texts)
        self.blockSignals(True)
        self.setPlainText(new_text)
        self.blockSignals(False)
        self._reparse_tags()
        # Re-apply syntax highlighting
        self._highlighter.rehighlight()

    def _apply_highlight(self, tag: _TagSpan) -> None:
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(_palette_color("selection_bg", 60))
        cursor = self.textCursor()
        cursor.setPosition(tag.start)
        cursor.setPosition(tag.end, QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cursor
        self.setExtraSelections([sel])

    def _clear_highlight(self) -> None:
        self.setExtraSelections([])

    def contextMenuEvent(self, event) -> None:
        self._show_local_context_menu(event.pos())
        event.accept()

    def _show_local_context_menu(self, pos: QPoint) -> None:
        # Suppress default context menu during scrub
        if self._scrub_tag is not None:
            return
        # Only show context menu if not on a tag (right-click on tag = scrub)
        tag = self._tag_at_cursor(pos)
        if tag:
            return
        if self._translator is not None:
            show_text_edit_context_menu(self, self._translator, self, self.mapToGlobal(pos))
            return

    def set_translator(self, translator: Translator) -> None:
        self._translator = translator


class _FlowLayout(QLayout):
    """Small wrapping layout mirroring the design稿 tag stream."""

    def __init__(self, parent=None, *, h_spacing: int = 4, v_spacing: int = 4) -> None:
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        margins = self.contentsMargins()
        width = 0
        for item in self._items:
            width = max(width, item.sizeHint().width())
        width += margins.left() + margins.right()
        height = self._do_layout(QRect(0, 0, max(width, 1), 0), True)
        height += margins.top() + margins.bottom()
        return QSize(width, height)

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        right = rect.right()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if next_x > right and line_height > 0:
                x = rect.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._h_spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class _TagHoverTip(QFrame):
    """Theme-aware hover card that mirrors the HTML tag-tip instead of Qt's native tooltip."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("WorkbenchTagHoverTip")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(_dp(8), _dp(6), _dp(8), _dp(10))
        layout.setSpacing(_dp(2))
        self._title = QLabel(self)
        self._title.setObjectName("WorkbenchTagHoverTipTitle")
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._meta = QLabel(self)
        self._meta.setObjectName("WorkbenchTagHoverTipMeta")
        self._meta.setTextFormat(Qt.TextFormat.PlainText)
        self._meta.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._title)
        layout.addWidget(self._meta)
        self._bg = _palette_color("bg_menu")
        self._border = _palette_color("line_strong")
        self.apply_style()

    def apply_style(self) -> None:
        pal = current_palette()
        self._bg = _palette_color("bg_menu")
        self._border = _palette_color("line_strong")
        self.setStyleSheet(
            "QFrame#WorkbenchTagHoverTip { background: transparent; border: none; }"
            f"QLabel#WorkbenchTagHoverTipTitle {{ color: {pal['text']}; background: transparent; font-size: {_fs('fs_11')}; }}"
            f"QLabel#WorkbenchTagHoverTipMeta {{ color: {pal['text_label']}; background: transparent; font-size: {_fs('fs_10')}; }}"
        )

    def show_tip(self, anchor_global: QPoint, title: str, meta: str) -> None:
        self._title.setText(title)
        self._meta.setText(meta)
        self._meta.setVisible(bool(meta))
        self.apply_style()
        self.adjustSize()
        parent = self.parentWidget()
        if parent is None:
            return
        width = self.sizeHint().width()
        height = self.sizeHint().height()
        x = anchor_global.x() - width // 2
        y = anchor_global.y() - height - _dp(6)
        top_left = parent.mapFromGlobal(QPoint(x, y))
        top_left.setX(max(_dp(6), min(top_left.x(), parent.width() - width - _dp(6))))
        top_left.setY(max(_dp(6), min(top_left.y(), parent.height() - height - _dp(6))))
        self.move(top_left)
        self.resize(width, height)
        self.show()
        self.raise_()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body = self.rect().adjusted(0, 0, 0, -_dp(5))
        painter.setPen(self._border)
        painter.setBrush(self._bg)
        painter.drawRoundedRect(body, _dp(4), _dp(4))
        cx = self.width() // 2
        triangle = QPolygon([
            QPoint(cx - _dp(4), body.bottom()),
            QPoint(cx + _dp(4), body.bottom()),
            QPoint(cx, self.rect().bottom()),
        ])
        painter.drawPolygon(triangle)
        super().paintEvent(event)


class _WorkbenchTagChip(QLabel):
    hover_requested = pyqtSignal(int, QPoint)
    hover_left = pyqtSignal()
    left_pressed = pyqtSignal(int, QPoint)
    left_moved = pyqtSignal(QPoint)
    left_released = pyqtSignal(QPoint)
    right_pressed = pyqtSignal(int, int)
    right_moved = pyqtSignal(int)
    right_released = pyqtSignal()

    def __init__(
        self,
        text: str,
        *,
        index: int,
        category: str,
        weight: float | None,
        dictionary: TagDictionary | None,
        translator: Translator,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self._raw_text = text
        self._raw_category = category
        self._category = _semantic_category(category)
        self._weight = weight
        self._translator = translator
        self._left_dragging = False
        self._right_dragging = False
        self._hovered = False
        self._scrubbing = False
        self.setText(self._display_text())
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setObjectName("WorkbenchTagChip")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.apply_style()

    def _display_text(self) -> str:
        if self._weight is None or abs(self._weight - 1.0) < 0.01:
            return escape(self._raw_text)
        badge_color = CATEGORY_COLORS.get("action" if self._weight > 1.0 else "character", "#a8a8a8")
        badge_bg = QColor(badge_color)
        badge_bg.setAlpha(30)
        return (
            f"{escape(self._raw_text)}"
            f"<span style='font-size: {_fs('fs_9')}; color: {badge_color}; "
            f"background-color: rgba({badge_bg.red()}, {badge_bg.green()}, {badge_bg.blue()}, {badge_bg.alpha() / 255:.3f}); "
            f"padding-left: 3px; padding-right: 3px; margin-left: 2px;'>"
            f"{escape(_format_weight(self._weight))}</span>"
        )

    def apply_style(self) -> None:
        pal = current_palette()
        colors = CATEGORY_COLORS_LIGHT if is_theme_light() else CATEGORY_COLORS
        color = colors.get(self._category) or colors['appearance']
        q = QColor(color)
        border = QColor(q)
        border.setAlpha(116 if self._hovered or self._scrubbing else 76)
        bg = QColor(q)
        bg.setAlpha(45 if self._hovered or self._scrubbing else 26)
        self.setStyleSheet(
            "QLabel#WorkbenchTagChip { "
            f"color: {color}; background: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {bg.alpha() / 255:.3f}); "
            f"border: 1px solid rgba({border.red()}, {border.green()}, {border.blue()}, {border.alpha() / 255:.3f}); "
            f"border-radius: {_dp(3)}px; padding: {_dp(2)}px {_dp(8)}px; "
            f"font-size: {_fs('fs_11')}; "
            "}"
            f"QLabel#WorkbenchTagChip:hover {{ background: {pal['hover_bg_strong']}; }}"
        )

    def set_hovered(self, hovered: bool) -> None:
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self.apply_style()

    def set_scrub_preview(self, weight: float) -> None:
        self._scrubbing = True
        self._weight = weight
        self.setText(self._display_text())
        self.apply_style()
        self.adjustSize()

    def finish_right_drag(self) -> None:
        if self._right_dragging:
            self._right_dragging = False
            self.releaseMouse()
        self._scrubbing = False
        self.apply_style()

    def enterEvent(self, event) -> None:
        self.set_hovered(True)
        self.hover_requested.emit(self._index, self.mapToGlobal(QPoint(self.width() // 2, 0)))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._right_dragging:
            self.set_hovered(False)
        self.hover_left.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._left_dragging = True
            self.grabMouse()
            self.left_pressed.emit(self._index, event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._right_dragging = True
            self._scrubbing = True
            self.apply_style()
            self.grabMouse()
            self.right_pressed.emit(self._index, event.globalPosition().toPoint().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._left_dragging:
            self.left_moved.emit(event.globalPosition().toPoint())
            event.accept()
            return
        if self._right_dragging:
            self.right_moved.emit(event.globalPosition().toPoint().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._left_dragging:
            self._left_dragging = False
            self.releaseMouse()
            self.left_released.emit(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton and self._right_dragging:
            self.finish_right_drag()
            self.right_released.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        event.accept()


class _TagStreamView(QScrollArea):
    """Visual chip stream for the workbench while keeping QTextEdit as data source."""

    def __init__(self, editor: TagTextEdit, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._translator = translator
        self._dictionary: TagDictionary | None = None
        self._chips: list[_WorkbenchTagChip] = []
        self._drag_index: int | None = None
        self._drag_origin: QPoint | None = None
        self._drag_target: int | None = None
        self._scrub_index: int | None = None
        self._scrub_origin_x = 0
        self._scrub_origin_weight = 1.0
        self._scrub_preview_weight = 1.0
        self._scrub_chip: _WorkbenchTagChip | None = None
        self._suppress_next_context_menu = False
        self._streaming = False
        self._hover_tip: _TagHoverTip | None = None
        self._hover_tip_parent: QWidget | None = None
        self.setObjectName("WorkbenchTagStream")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget(self)
        self._inner.setObjectName("WorkbenchTagStreamInner")
        self._flow = _FlowLayout(self._inner, h_spacing=_dp(4), v_spacing=_dp(4))
        self._flow.setContentsMargins(0, 0, 0, 0)
        self.setWidget(self._inner)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._empty = QLabel(self._translator.t("output_waiting_tag"), self.viewport())
        self._empty.setObjectName("WorkbenchTagEmpty")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.textChanged.connect(self.refresh)
        self.refresh()
        self.apply_style()

    def set_dictionary(self, dictionary: TagDictionary) -> None:
        self._dictionary = dictionary
        self.refresh()

    def set_streaming(self, streaming: bool) -> None:
        if self._streaming == streaming:
            return
        self._streaming = streaming
        if streaming:
            while self._flow.count():
                item = self._flow.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._chips = []
            self._empty.setVisible(False)
        else:
            self.refresh()

    def refresh(self) -> None:
        if self._streaming:
            return
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._chips = []
        text = self._editor.toPlainText().strip()
        tags = self._parse_tags(text)
        self._empty.setVisible(not tags)
        for idx, (name, weight) in enumerate(tags):
            norm = name.lower().replace(' ', '_')
            category = self._editor._tag_categories.get(norm) or _tag_semantic_from_dictionary(self._dictionary, name)
            chip = _WorkbenchTagChip(
                name,
                index=idx,
                category=category,
                weight=weight,
                dictionary=self._dictionary,
                translator=self._translator,
                parent=self._inner,
            )
            chip.hover_requested.connect(self._show_chip_tip)
            chip.hover_left.connect(self._hide_chip_tip)
            chip.left_pressed.connect(self._begin_chip_drag)
            chip.left_moved.connect(self._move_chip_drag)
            chip.left_released.connect(self._finish_chip_drag)
            chip.right_pressed.connect(self._begin_chip_scrub)
            chip.right_moved.connect(self._move_chip_scrub)
            chip.right_released.connect(self._finish_chip_scrub)
            self._chips.append(chip)
            self._flow.addWidget(chip)
        self._inner.adjustSize()

    def retranslate_ui(self) -> None:
        self._empty.setText(self._translator.t("output_waiting_tag"))

    def mouseDoubleClickEvent(self, event) -> None:
        editor = self._editor
        self.hide()
        editor.show()
        editor.setFocus()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self._scrub_index is not None or self._suppress_next_context_menu or self._chip_at_global(event.globalPos()) is not None:
            self._suppress_next_context_menu = False
            event.accept()
            return
        show_text_edit_context_menu(
            self._editor,
            self._translator,
            self,
            event.globalPos(),
        )
        event.accept()

    def eventFilter(self, watched, event) -> bool:
        if self._scrub_index is not None:
            event_type = event.type()
            if event_type == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                self._move_chip_scrub(event.globalPosition().toPoint().x())
                return True
            if event_type == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
                if event.button() == Qt.MouseButton.RightButton:
                    self._move_chip_scrub(event.globalPosition().toPoint().x())
                    self._finish_chip_scrub()
                    return True
            if event_type == QEvent.Type.ContextMenu:
                self._suppress_next_context_menu = False
                return True
            if event_type in (QEvent.Type.WindowDeactivate, QEvent.Type.FocusOut, QEvent.Type.Hide):
                self._finish_chip_scrub()
        return super().eventFilter(watched, event)

    def _ensure_hover_tip(self) -> _TagHoverTip:
        parent = self.window()
        if not isinstance(parent, QWidget):
            parent = self
        if self._hover_tip is None or self._hover_tip_parent is not parent:
            if self._hover_tip is not None:
                self._hover_tip.deleteLater()
            self._hover_tip = _TagHoverTip(parent)
            self._hover_tip_parent = parent
        return self._hover_tip

    def _hide_chip_tip(self) -> None:
        if self._hover_tip is not None:
            self._hover_tip.hide()

    def _show_chip_tip(self, index: int, global_pos: QPoint) -> None:
        if self._scrub_index is not None:
            return
        if not (0 <= index < len(self._editor._tags)):
            return
        tag = self._editor._tags[index]
        dictionary = self._dictionary or self._editor._dictionary
        info = dictionary.lookup(tag.name) if dictionary is not None else None
        title = info.translation if info is not None and info.translation else tag.name
        if dictionary is not None:
            cat = tag.category or _tag_semantic_from_dictionary(dictionary, tag.name)
        else:
            cat = tag.category or "appearance"
        display_category = _category_display_name(self._translator, cat)
        if info is not None:
            count_text = self._translator.t("tag_posts_count").format(count=f"{info.count:,}")
            meta = f"{display_category} · {count_text}"
        else:
            meta = display_category
        self._ensure_hover_tip().show_tip(global_pos, title, meta)

    def _begin_chip_scrub(self, index: int, global_x: int) -> None:
        if not (0 <= index < len(self._editor._tags)):
            return
        self._hide_chip_tip()
        self._scrub_index = index
        self._scrub_origin_x = global_x
        self._scrub_origin_weight = self._editor._tags[index].weight
        self._scrub_preview_weight = self._scrub_origin_weight
        self._scrub_chip = self._chips[index] if 0 <= index < len(self._chips) else None
        self._suppress_next_context_menu = True
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
            app.installEventFilter(self)

    def _move_chip_scrub(self, global_x: int) -> None:
        if self._scrub_index is None or not (0 <= self._scrub_index < len(self._editor._tags)):
            return
        dx = global_x - self._scrub_origin_x
        delta = dx * _weight_scrub_step()
        new_weight = round(max(0.1, min(2.0, self._scrub_origin_weight + delta)), 2)
        if new_weight == self._scrub_preview_weight:
            return
        self._scrub_preview_weight = new_weight
        if 0 <= self._scrub_index < len(self._chips):
            self._chips[self._scrub_index].set_scrub_preview(new_weight)
            self._inner.adjustSize()

    def _finish_chip_scrub(self) -> None:
        if self._scrub_index is None:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        index = self._scrub_index
        final_weight = self._scrub_preview_weight
        chip = self._scrub_chip
        self._scrub_index = None
        self._scrub_chip = None
        self.unsetCursor()
        if chip is not None:
            chip.finish_right_drag()
        if 0 <= index < len(self._editor._tags):
            tag = self._editor._tags[index]
            if abs(tag.weight - final_weight) >= 0.001:
                self._editor._apply_weight(tag, final_weight)
                self._editor._reparse_tags()
                self._editor._highlighter.rehighlight()
        self.refresh()
        self._editor.textChanged.emit()

    def _begin_chip_drag(self, index: int, global_pos: QPoint) -> None:
        if not (0 <= index < len(self._editor._tags)):
            return
        self._drag_index = index
        self._drag_target = index
        self._drag_origin = global_pos
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _move_chip_drag(self, global_pos: QPoint) -> None:
        if self._drag_index is None:
            return
        target = self._chip_insertion_index_at(global_pos)
        if target is not None:
            self._drag_target = target

    def _finish_chip_drag(self, global_pos: QPoint) -> None:
        if self._drag_index is None:
            return
        target = self._chip_insertion_index_at(global_pos)
        if target is not None:
            self._drag_target = target
        src = self._drag_index
        dst = self._drag_target if self._drag_target is not None else src
        self._drag_index = None
        self._drag_target = None
        self._drag_origin = None
        self.unsetCursor()
        if (
            not (0 <= src < len(self._editor._tags))
            or not (0 <= dst <= len(self._editor._tags))
            or dst in (src, src + 1)
        ):
            return
        text = self._editor.toPlainText()
        tag_texts = [text[tag.start:tag.end].strip() for tag in self._editor._tags]
        moved = tag_texts.pop(src)
        if dst > src:
            dst -= 1
        tag_texts.insert(dst, moved)
        self._editor.setPlainText(", ".join(tag_texts))
        self._editor._highlighter.rehighlight()

    def _chip_insertion_index_at(self, global_pos: QPoint) -> int | None:
        local = self._inner.mapFromGlobal(global_pos)
        child = self._inner.childAt(local)
        while child is not None and not isinstance(child, _WorkbenchTagChip):
            child = child.parentWidget()
        if isinstance(child, _WorkbenchTagChip):
            return child._index if local.x() < child.geometry().center().x() else child._index + 1
        if not self._chips:
            return None
        row_margin = _dp(6)
        for chip in self._chips:
            geom = chip.geometry()
            if local.y() <= geom.bottom() + row_margin:
                if local.x() < geom.center().x():
                    return chip._index
                row_end = chip._index + 1
                continue
            if "row_end" in locals():
                return row_end
        return len(self._chips)

    def _chip_at_global(self, global_pos: QPoint) -> _WorkbenchTagChip | None:
        local = self._inner.mapFromGlobal(global_pos)
        child = self._inner.childAt(local)
        while child is not None and not isinstance(child, _WorkbenchTagChip):
            child = child.parentWidget()
        return child if isinstance(child, _WorkbenchTagChip) else None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._empty.setGeometry(self.viewport().rect())
        width = max(0, self.viewport().width() - _dp(2))
        height = max(self.viewport().height(), self._flow.heightForWidth(width))
        self._inner.setMinimumSize(width, height)

    def apply_style(self) -> None:
        pal = current_palette()
        self.setStyleSheet(
            "QScrollArea#WorkbenchTagStream { background: transparent; border: none; }"
            "QWidget#WorkbenchTagStreamInner { background: transparent; }"
            f"QLabel#WorkbenchTagEmpty {{ color: {pal['text_label']}; background: transparent; font-size: {_fs('fs_12')}; }}"
            f"QScrollBar:vertical {{ background: transparent; width: {_dp(8)}px; }}"
            f"QScrollBar::handle:vertical {{ background: {pal['scrollbar']}; border-radius: {_dp(4)}px; min-height: {_dp(24)}px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        if self._hover_tip is not None:
            self._hover_tip.apply_style()
        self.refresh()

    @staticmethod
    def _parse_tags(text: str) -> list[tuple[str, float | None]]:
        result: list[tuple[str, float | None]] = []
        for raw in text.replace('\n', ',').split(','):
            stripped = raw.strip()
            if not stripped:
                continue
            m = _SD_WEIGHT_RE.match(stripped)
            if m:
                result.append((m.group(1).strip(), float(m.group(2))))
            else:
                result.append((stripped.strip('(){}[] '), None))
        return result


class OutputWidget(QWidget):
    """TAG workbench: displays generated TAGs with hover translation and weight editing."""

    changed = pyqtSignal()

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.setObjectName("WorkbenchOutput")
        self._tab_bar = QWidget(self)
        self._tab_bar.setObjectName("WorkbenchTabs")
        tab_layout = QHBoxLayout(self._tab_bar)
        tab_layout.setContentsMargins(_dp(16), _dp(12), _dp(16), 0)
        tab_layout.setSpacing(_dp(22))
        self.full_tab_button = QPushButton(self._tab_bar)
        self.full_tab_button.setCheckable(True)
        self.full_tab_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.full_tab_button.clicked.connect(lambda: self._set_active_tab(0))
        self.nochar_tab_button = QPushButton(self._tab_bar)
        self.nochar_tab_button.setCheckable(True)
        self.nochar_tab_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.nochar_tab_button.clicked.connect(lambda: self._set_active_tab(1))
        tab_layout.addWidget(self.full_tab_button)
        tab_layout.addWidget(self.nochar_tab_button)
        tab_layout.addStretch(1)
        root.addWidget(self._tab_bar, 0)

        self._output_frame = QFrame(self)
        self._output_frame.setObjectName("WorkbenchOutputFrame")
        output_frame_layout = QVBoxLayout(self._output_frame)
        output_frame_layout.setContentsMargins(0, 0, 0, 0)
        output_frame_layout.setSpacing(0)
        self._status_pill = QLabel(self._output_frame)
        self._status_pill.setObjectName("WorkbenchStatusPill")
        self._status_pill.hide()
        self.stack = QStackedWidget(self._output_frame)
        output_frame_layout.addWidget(self.stack, 1)
        root.addWidget(self._output_frame, 1)

        # Full TAG tab
        full_container = QWidget()
        full_layout = QVBoxLayout(full_container)
        full_layout.setContentsMargins(_dp(12), _dp(10), _dp(12), _dp(10))
        full_layout.setSpacing(0)
        self.full_editor = TagTextEdit(self._translator, full_container)
        self.full_editor.setProperty('class', 'OutputEditor')
        self.full_editor.textChanged.connect(self.changed)
        self.full_editor.installEventFilter(self)
        self.full_tag_stream = _TagStreamView(self.full_editor, self._translator, full_container)
        self.full_editor.hide()
        full_layout.addWidget(self.full_tag_stream, 1)
        full_layout.addWidget(self.full_editor, 1)
        self.stack.addWidget(full_container)

        # No-character TAG tab
        nochar_container = QWidget()
        nochar_layout = QVBoxLayout(nochar_container)
        nochar_layout.setContentsMargins(_dp(12), _dp(10), _dp(12), _dp(10))
        nochar_layout.setSpacing(0)
        self.nochar_editor = TagTextEdit(self._translator, nochar_container)
        self.nochar_editor.setProperty('class', 'OutputEditor')
        self.nochar_editor.textChanged.connect(self.changed)
        self.nochar_editor.installEventFilter(self)
        self.nochar_tag_stream = _TagStreamView(self.nochar_editor, self._translator, nochar_container)
        self.nochar_editor.hide()
        nochar_layout.addWidget(self.nochar_tag_stream, 1)
        nochar_layout.addWidget(self.nochar_editor, 1)
        self.stack.addWidget(nochar_container)

        self._copy_bar = QWidget(self)
        self._copy_bar.setObjectName("WorkbenchCopyBar")
        copy_layout = QHBoxLayout(self._copy_bar)
        copy_layout.setContentsMargins(_dp(16), _dp(8), _dp(16), _dp(8))
        copy_layout.setSpacing(_dp(6))
        self.edit_toggle_button = QPushButton(self._copy_bar)
        self.edit_toggle_button.setObjectName("WorkbenchCopyButton")
        self.edit_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_toggle_button.clicked.connect(self._toggle_edit_mode)
        copy_layout.addWidget(self.edit_toggle_button)
        copy_layout.addStretch(1)
        self.copy_button = QPushButton(self._copy_bar)
        self.copy_button.setObjectName("WorkbenchCopyButton")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self._copy_current)
        copy_layout.addWidget(self.copy_button)
        root.addWidget(self._copy_bar, 0)

        self._edit_mode = False
        self._tag_dictionary = None
        self.retranslate_ui()
        self._set_active_tab(0)
        self.apply_workbench_style()

    def eventFilter(self, watched, event) -> bool:
        if (
            hasattr(self, "full_tag_stream")
            and hasattr(self, "nochar_tag_stream")
            and watched in (self.full_editor, self.nochar_editor)
            and event.type() == QEvent.Type.FocusOut
            and not self._edit_mode
        ):
            self._show_stream_for_current_tab()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_status_pill()

    def _position_status_pill(self) -> None:
        if not self._status_pill.isVisible():
            return
        self._status_pill.adjustSize()
        self._status_pill.move(
            max(0, self._output_frame.width() - self._status_pill.width() - _dp(8)),
            _dp(8),
        )

    def retranslate_ui(self) -> None:
        t = self._translator.t
        self.full_tab_button.setText(t('full_tags'))
        self.nochar_tab_button.setText(t('nochar_tags'))
        self.copy_button.setText(t('copy'))
        self._refresh_edit_toggle_label()
        self.full_editor.set_translator(self._translator)
        self.nochar_editor.set_translator(self._translator)
        self.full_editor.setPlaceholderText(t('output_waiting_tag'))
        self.nochar_editor.setPlaceholderText(t('output_waiting_tag'))
        self.full_tag_stream.retranslate_ui()
        self.nochar_tag_stream.retranslate_ui()

    def _refresh_edit_toggle_label(self) -> None:
        t = self._translator.t
        key = 'output_view_mode' if self._edit_mode else 'output_edit_mode'
        fallback = '◧ 视图' if self._edit_mode else '✏ 编辑'
        text = t(key)
        if not text or text == key:
            text = fallback
        self.edit_toggle_button.setText(text)

    def _toggle_edit_mode(self) -> None:
        self._edit_mode = not self._edit_mode
        self._refresh_edit_toggle_label()
        self._show_stream_for_current_tab()
        if self._edit_mode:
            current_editor = self.full_editor if self.stack.currentIndex() == 0 else self.nochar_editor
            current_editor.setFocus()

    def is_edit_mode(self) -> bool:
        return self._edit_mode

    def set_tag_dictionary(self, dictionary) -> None:
        from .tag_completer import install_completer_recursive
        self._tag_dictionary = dictionary
        self.full_editor.set_dictionary(dictionary)
        self.nochar_editor.set_dictionary(dictionary)
        self.full_tag_stream.set_dictionary(dictionary)
        self.nochar_tag_stream.set_dictionary(dictionary)
        install_completer_recursive(self, dictionary)

    def _set_active_tab(self, index: int) -> None:
        index = 1 if index == 1 else 0
        self.stack.setCurrentIndex(index)
        self.full_tab_button.setChecked(index == 0)
        self.nochar_tab_button.setChecked(index == 1)
        self._show_stream_for_current_tab()
        self._refresh_tab_styles()

    def _refresh_tab_styles(self) -> None:
        pal = current_palette()
        for button in (self.full_tab_button, self.nochar_tab_button):
            active = button.isChecked()
            button.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-bottom: {_dp(2) if active else 0}px solid "
                f"{pal['accent_text'] if active else 'transparent'}; color: {pal['text'] if active else pal['text_label']}; "
                f"font-size: {_fs('fs_13')}; font-weight: {'500' if active else '400'}; "
                f"padding: 0px 0px {_dp(8)}px 0px; }}"
                f"QPushButton:hover {{ color: {pal['text']}; }}"
            )

    def apply_workbench_style(self) -> None:
        pal = current_palette()
        self.setStyleSheet(
            f"QWidget#WorkbenchOutput {{ background: {pal['bg_card_strip']}; }}"
            f"QWidget#WorkbenchTabs {{ background: {pal['bg_card_strip']}; }}"
            f"QFrame#WorkbenchOutputFrame {{ background: {pal['bg_surface']}; border: 1px solid {pal['line']}; border-radius: {_dp(4)}px; margin: 0px {_dp(16)}px 0px {_dp(16)}px; }}"
            f"QWidget#WorkbenchCopyBar {{ background: {pal['bg_card_strip']}; }}"
            f"QPushButton#WorkbenchCopyButton {{ background: {pal['bg_surface']}; color: {pal['text']}; border: 1px solid {pal['line_hover']}; border-radius: {_dp(4)}px; padding: {_dp(5)}px {_dp(12)}px; font-size: {_fs('fs_12')}; }}"
            f"QPushButton#WorkbenchCopyButton:hover {{ background: {pal['hover_bg_strong']}; }}"
            f"QLabel#WorkbenchStatusPill {{ background: {pal['bg_menu']}; color: {pal['text_muted']}; border: 1px solid {pal['line_hover']}; border-radius: {_dp(10)}px; padding: {_dp(3)}px {_dp(8)}px; font-size: {_fs('fs_11')}; }}"
            f"QTextEdit[class=\"OutputEditor\"] {{ background: transparent; color: {pal['text']}; border: none; "
            f"font-size: {_fs('fs_12')}; selection-background-color: {pal['selection_bg']}; }}"
            f"QScrollBar:vertical {{ background: transparent; width: {_dp(8)}px; }}"
            f"QScrollBar::handle:vertical {{ background: {pal['scrollbar']}; border-radius: {_dp(4)}px; min-height: {_dp(24)}px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        self.full_tag_stream.apply_style()
        self.nochar_tag_stream.apply_style()
        self._refresh_tab_styles()
        self._position_status_pill()

    def set_generation_status(self, status: str, text: str = "") -> None:
        pal = current_palette()
        labels = {
            "running": "● " + self._translator.t("generation_running"),
            "done": "● " + self._translator.t("generation_done"),
            "error": "● " + self._translator.t("generation_error"),
        }
        label = text or labels.get(status, "")
        self._status_pill.setText(label)
        self._status_pill.setVisible(bool(label))
        dot_color = pal['accent_text'] if status == "running" else CATEGORY_COLORS.get("scene", pal['text']) if status == "done" else CATEGORY_COLORS.get("emotion", pal['text'])
        self._status_pill.setStyleSheet(
            f"QLabel#WorkbenchStatusPill {{ background: {pal['bg_menu']}; color: {pal['text_muted']}; "
            f"border: 1px solid {pal['line_hover']}; border-radius: {_dp(10)}px; padding: {_dp(3)}px {_dp(8)}px; font-size: {_fs('fs_11')}; }}"
            f"QLabel#WorkbenchStatusPill {{ color: {dot_color}; }}"
        )
        self._position_status_pill()

    def set_full_tags(self, text: str) -> None:
        self.full_editor.setPlainText(text)
        self._show_stream_for_current_tab()

    def set_nochar_tags(self, text: str) -> None:
        self.nochar_editor.setPlainText(text)
        self._show_stream_for_current_tab()

    def set_tag_categories(self, categories: dict[str, str]) -> None:
        mapping = dict(categories or {})
        self.full_editor.set_tag_categories(mapping)
        self.nochar_editor.set_tag_categories(mapping)
        self.full_tag_stream.refresh()
        self.nochar_tag_stream.refresh()
        self._show_stream_for_current_tab()

    def tag_categories(self) -> dict[str, str]:
        return dict(self.full_editor._tag_categories)

    def append_full_text(self, text: str) -> None:
        cursor = self.full_editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.full_editor.setTextCursor(cursor)
        if not self.full_tag_stream._streaming:
            self.full_tag_stream.refresh()
            self._show_stream_for_current_tab()

    def set_streaming(self, streaming: bool) -> None:
        self.full_tag_stream.set_streaming(streaming)
        self.nochar_tag_stream.set_streaming(streaming)
        if streaming:
            self.full_tag_stream.hide()
            self.nochar_tag_stream.hide()
            self.full_editor.show()
            self.nochar_editor.show()
        else:
            self._show_stream_for_current_tab()

    def set_dictionary(self, dictionary: TagDictionary) -> None:
        self.full_editor.set_dictionary(dictionary)
        self.nochar_editor.set_dictionary(dictionary)
        self.full_tag_stream.set_dictionary(dictionary)
        self.nochar_tag_stream.set_dictionary(dictionary)

    def apply_post_processing(
        self,
        tag_full_start: str = "[TAGS]",
        tag_full_end: str = "[/TAGS]",
        tag_nochar_start: str = "[NOTAGS]",
        tag_nochar_end: str = "[/NOTAGS]",
    ) -> None:
        """After streaming completes, extract tags by markers and apply category highlighting.

        Pipeline:
        1. Extract [TAGS]...[/TAGS] → full_editor (if markers found)
        2. Extract [NOTAGS]...[/NOTAGS] → nochar_editor (if markers found)
        3. Split §category¦tag mapping from full_editor text
        4. Apply syntax highlighting by category
        """
        raw = self.full_editor.toPlainText()

        # Step 1: extract full tags by markers
        full_extracted = extract_by_markers(raw, tag_full_start, tag_full_end)
        if full_extracted is not None:
            full_text = full_extracted
        else:
            full_text = raw.strip()

        # Step 2: extract nochar tags by markers (from original raw text)
        nochar_extracted = extract_by_markers(raw, tag_nochar_start, tag_nochar_end)
        if nochar_extracted is not None:
            self.nochar_editor.blockSignals(True)
            self.nochar_editor.setPlainText(nochar_extracted)
            self.nochar_editor.blockSignals(False)

        # Step 3: split §category mapping from full tags
        clean, mapping = split_tags_and_mapping(full_text)

        # Step 4: update full_editor if content changed
        if clean != raw or full_extracted is not None:
            self.full_editor.blockSignals(True)
            self.full_editor.setPlainText(clean)
            self.full_editor.blockSignals(False)
            self.full_editor._reparse_tags()

        self.full_editor.set_tag_categories(mapping)
        self.nochar_editor.set_tag_categories(mapping)
        self.nochar_editor._reparse_tags()
        self.full_tag_stream.refresh()
        self.nochar_tag_stream.refresh()
        self._show_stream_for_current_tab()

    def refresh_highlighter(self) -> None:
        """Re-apply syntax highlighting after theme change."""
        self.full_editor._highlighter.rehighlight()
        self.nochar_editor._highlighter.rehighlight()
        self.apply_workbench_style()

    def clear_output(self) -> None:
        self.full_editor.clear()
        self.nochar_editor.clear()
        self.full_editor.set_tag_categories({})
        self.nochar_editor.set_tag_categories({})
        self.full_tag_stream.refresh()
        self.nochar_tag_stream.refresh()
        self.set_generation_status("")
        self._show_stream_for_current_tab()

    def _copy(self, editor: TagTextEdit) -> None:
        text = editor.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)

    def _copy_current(self) -> None:
        editor = self.full_editor if self.stack.currentIndex() == 0 else self.nochar_editor
        self._copy(editor)

    def _show_stream_for_current_tab(self) -> None:
        full_active = self.stack.currentIndex() == 0
        nochar_active = self.stack.currentIndex() == 1
        if self._edit_mode:
            self.full_tag_stream.hide()
            self.nochar_tag_stream.hide()
            self.full_editor.setVisible(full_active)
            self.nochar_editor.setVisible(nochar_active)
        else:
            self.full_editor.hide()
            self.nochar_editor.hide()
            self.full_tag_stream.setVisible(full_active)
            self.nochar_tag_stream.setVisible(nochar_active)
