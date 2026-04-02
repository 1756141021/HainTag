from __future__ import annotations

import re
from dataclasses import dataclass, field

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QMouseEvent,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..tag_dictionary import TagDictionary
from ..theme import is_theme_light

# Regex to parse a single tag's weight: (tag:1.3) or plain tag
_SD_WEIGHT_RE = re.compile(r'\(([^()]+):(\d+\.?\d*)\)')

# ── TAG category system ──
# Separator: § = category block, ¦ = tag within block
_CATEGORY_SEPARATOR = '§'
_CATEGORY_TAG_SEP = '¦'
_CATEGORY_BLOCK_RE = re.compile(r'§(\w+)((?:¦[^§¦]+)+)')


CATEGORY_COLORS: dict[str, str] = {
    'character':  '#00ab2c',
    'scene':      '#50a060',
    'pose':       '#e06050',
    'clothing':   '#c09050',
    'expression': '#d08080',
    'body':       '#6090c0',
    'style':      '#a070c0',
    'quality':    '#7c8a99',
}

CATEGORY_COLORS_LIGHT: dict[str, str] = {
    'character':  '#008820',
    'scene':      '#3a7a48',
    'pose':       '#c04838',
    'clothing':   '#9a7038',
    'expression': '#b06060',
    'body':       '#4870a0',
    'style':      '#7a50a0',
    'quality':    '#5a6670',
}


def parse_category_mapping(raw: str) -> dict[str, str]:
    """Parse §category¦tag1¦tag2§category2¦tag3 → {tag: category}."""
    mapping: dict[str, str] = {}
    for m in _CATEGORY_BLOCK_RE.finditer(raw):
        cat = m.group(1).lower()
        tags_part = m.group(2)  # ¦tag1¦tag2
        for tag in tags_part.split(_CATEGORY_TAG_SEP):
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
        pos = 0
        for raw_tag in text.split(','):
            start = pos
            end = pos + len(raw_tag)
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
            pos = end + 1  # +1 for comma


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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
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
        pos = 0
        for raw_tag in text.split(','):
            start = pos
            end = pos + len(raw_tag)
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
            pos = end + 1  # +1 for the comma

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
                    lines.append(f'[{tag.category}]')
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
        delta = dx * 0.005  # ~0.05 per 10px
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
            new_tag_core = f'({tag.name}:{new_weight})'

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
            sel.format.setBackground(QColor(100, 120, 220, 40) if not is_theme_light() else QColor(80, 100, 180, 30))
            sel.format.setForeground(QColor(150, 150, 150))
            c = self.textCursor()
            c.setPosition(self._drag_candidate.start)
            c.setPosition(self._drag_candidate.end, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            selections.append(sel)
        # Highlight drop target tag (accent border)
        if 0 <= self._drag_target_idx < len(self._tags):
            target = self._tags[self._drag_target_idx]
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(100, 200, 120, 60) if not is_theme_light() else QColor(60, 160, 80, 45))
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
        if is_theme_light():
            sel.format.setBackground(QColor(80, 100, 180, 45))
        else:
            sel.format.setBackground(QColor(100, 120, 220, 60))
        cursor = self.textCursor()
        cursor.setPosition(tag.start)
        cursor.setPosition(tag.end, QTextCursor.MoveMode.KeepAnchor)
        sel.cursor = cursor
        self.setExtraSelections([sel])

    def _clear_highlight(self) -> None:
        self.setExtraSelections([])

    def contextMenuEvent(self, event) -> None:
        # Suppress default context menu during scrub
        if self._scrub_tag is not None:
            event.accept()
            return
        # Only show context menu if not on a tag (right-click on tag = scrub)
        tag = self._tag_at_cursor(event.pos())
        if tag:
            event.accept()
            return
        super().contextMenuEvent(event)


class OutputWidget(QWidget):
    """TAG workbench: displays generated TAGs with hover translation and weight editing."""

    changed = pyqtSignal()

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName('OutputTabs')

        # Full TAG tab
        full_container = QWidget()
        full_layout = QVBoxLayout(full_container)
        full_layout.setContentsMargins(4, 4, 4, 4)
        full_layout.setSpacing(4)
        self.full_editor = TagTextEdit(full_container)
        self.full_editor.setProperty('class', 'OutputEditor')
        self.full_editor.textChanged.connect(self.changed)
        full_layout.addWidget(self.full_editor, 1)
        full_btn_row = QHBoxLayout()
        full_btn_row.setSpacing(6)
        full_btn_row.addStretch()
        self.copy_full_button = QPushButton('', full_container)
        self.copy_full_button.setObjectName('SecondaryButton')
        self.copy_full_button.clicked.connect(lambda: self._copy(self.full_editor))
        full_btn_row.addWidget(self.copy_full_button)
        full_layout.addLayout(full_btn_row)
        self.tabs.addTab(full_container, '')

        # No-character TAG tab
        nochar_container = QWidget()
        nochar_layout = QVBoxLayout(nochar_container)
        nochar_layout.setContentsMargins(4, 4, 4, 4)
        nochar_layout.setSpacing(4)
        self.nochar_editor = TagTextEdit(nochar_container)
        self.nochar_editor.setProperty('class', 'OutputEditor')
        self.nochar_editor.textChanged.connect(self.changed)
        nochar_layout.addWidget(self.nochar_editor, 1)
        nochar_btn_row = QHBoxLayout()
        nochar_btn_row.setSpacing(6)
        nochar_btn_row.addStretch()
        self.copy_nochar_button = QPushButton('', nochar_container)
        self.copy_nochar_button.setObjectName('SecondaryButton')
        self.copy_nochar_button.clicked.connect(lambda: self._copy(self.nochar_editor))
        nochar_btn_row.addWidget(self.copy_nochar_button)
        nochar_layout.addLayout(nochar_btn_row)
        self.tabs.addTab(nochar_container, '')

        root.addWidget(self.tabs)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        t = self._translator.t
        self.tabs.setTabText(0, t('full_tags'))
        self.tabs.setTabText(1, t('nochar_tags'))
        self.copy_full_button.setText(t('copy'))
        self.copy_nochar_button.setText(t('copy'))

    def set_full_tags(self, text: str) -> None:
        self.full_editor.setPlainText(text)

    def set_nochar_tags(self, text: str) -> None:
        self.nochar_editor.setPlainText(text)

    def append_full_text(self, text: str) -> None:
        cursor = self.full_editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.full_editor.setTextCursor(cursor)

    def set_dictionary(self, dictionary: TagDictionary) -> None:
        self.full_editor.set_dictionary(dictionary)
        self.nochar_editor.set_dictionary(dictionary)

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

        if mapping:
            self.full_editor.set_tag_categories(mapping)

    def refresh_highlighter(self) -> None:
        """Re-apply syntax highlighting after theme change."""
        self.full_editor._highlighter.rehighlight()
        self.nochar_editor._highlighter.rehighlight()

    def clear_output(self) -> None:
        self.full_editor.clear()
        self.nochar_editor.clear()
        self.full_editor.set_tag_categories({})
        self.nochar_editor.set_tag_categories({})

    def _copy(self, editor: TagTextEdit) -> None:
        text = editor.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
