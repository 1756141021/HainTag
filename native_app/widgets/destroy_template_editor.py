"""Destroy Template Editor — dialog for managing metadata destroy text presets."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..theme import _fs, current_palette


class DestroyTemplateEditor(QDialog):
    """Dialog for editing destroy text presets, similar to prompt manager style."""

    def __init__(self, templates: list[dict], active_index: int,
                 translator: Translator, parent=None):
        super().__init__(parent)
        self._t = translator
        self._templates = [dict(t) for t in templates]  # deep copy

        p = current_palette()
        self.setWindowTitle(translator.t("metadata_edit_preset"))
        self.setMinimumSize(500, 400)
        self.setStyleSheet(f"background: {p['bg']}; color: {p['text']};")

        root = QHBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Left: template list ──
        left = QVBoxLayout()
        left.setSpacing(6)

        left_header = QHBoxLayout()
        left_label = QLabel(translator.t("metadata_edit_preset"), self)
        left_label.setStyleSheet(f"font-size: {_fs('fs_12')}; font-weight: bold;")
        left_header.addWidget(left_label)
        left_header.addStretch()

        add_btn = QPushButton("+", self)
        add_btn.setFixedSize(24, 24)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: none; border-radius: 4px; font-size: {_fs('fs_12')}; font-weight: bold;"
        )
        add_btn.clicked.connect(self._add_template)
        left_header.addWidget(add_btn)

        left.addLayout(left_header)

        self._list = QListWidget(self)
        self._list.setStyleSheet(
            f"QListWidget {{ background: {p['bg_input']}; border: 1px solid {p['line']}; "
            f"border-radius: 4px; font-size: {_fs('fs_10')}; }}"
            f"QListWidget::item {{ padding: 6px 8px; }}"
            f"QListWidget::item:selected {{ background: {p['accent']}; color: {p['accent_text']}; }}"
        )
        self._list.currentRowChanged.connect(self._on_select)
        left.addWidget(self._list, 1)

        del_btn = QPushButton(translator.t("delete") if hasattr(translator, 'delete') else "删除", self)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            f"background: {p['delete_hover']}; color: {p['text']}; "
            f"border: none; border-radius: 4px; padding: 4px 12px; font-size: {_fs('fs_10')};"
        )
        del_btn.clicked.connect(self._delete_template)
        left.addWidget(del_btn)

        root.addLayout(left, 1)

        # ── Right: edit fields ──
        right = QVBoxLayout()
        right.setSpacing(8)

        name_label = QLabel("名称", self)
        name_label.setStyleSheet(f"font-size: {_fs('fs_10')}; color: {p['text_dim']};")
        right.addWidget(name_label)

        self._name_edit = QLineEdit(self)
        self._name_edit.setStyleSheet(
            f"background: {p['bg_input']}; color: {p['text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 4px 8px; font-size: {_fs('fs_11')};"
        )
        self._name_edit.textChanged.connect(self._on_name_changed)
        right.addWidget(self._name_edit)

        text_label = QLabel("销毁填充文本", self)
        text_label.setStyleSheet(f"font-size: {_fs('fs_10')}; color: {p['text_dim']};")
        right.addWidget(text_label)

        self._text_edit = QTextEdit(self)
        self._text_edit.setStyleSheet(
            f"background: {p['bg_input']}; color: {p['text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px 8px; font-size: {_fs('fs_10')};"
        )
        self._text_edit.textChanged.connect(self._on_text_changed)
        right.addWidget(self._text_edit, 1)

        # Save / Cancel buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton(translator.t("cancel"), self)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px 16px; font-size: {_fs('fs_10')};"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton(translator.t("ok"), self)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            f"color: {p['accent_text']}; background: {p['accent']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 6px 20px; font-size: {_fs('fs_11')}; font-weight: bold;"
        )
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        right.addLayout(btn_row)
        root.addLayout(right, 2)

        # Populate
        self._populating = False
        self._populate_list()
        if 0 <= active_index < len(self._templates):
            self._list.setCurrentRow(active_index)

    def _populate_list(self):
        self._populating = True
        self._list.clear()
        for t in self._templates:
            self._list.addItem(t["name"])
        self._populating = False

    def _on_select(self, row: int):
        if row < 0 or row >= len(self._templates):
            self._name_edit.clear()
            self._text_edit.clear()
            return
        t = self._templates[row]
        self._populating = True
        self._name_edit.setText(t["name"])
        self._text_edit.setPlainText(t["text"])
        self._populating = False

    def _on_name_changed(self, text: str):
        if self._populating:
            return
        row = self._list.currentRow()
        if 0 <= row < len(self._templates):
            self._templates[row]["name"] = text
            self._list.item(row).setText(text)

    def _on_text_changed(self):
        if self._populating:
            return
        row = self._list.currentRow()
        if 0 <= row < len(self._templates):
            self._templates[row]["text"] = self._text_edit.toPlainText()

    def _add_template(self):
        new = {"name": f"新预设 {len(self._templates) + 1}", "text": ""}
        self._templates.append(new)
        self._list.addItem(new["name"])
        self._list.setCurrentRow(len(self._templates) - 1)

    def _delete_template(self):
        row = self._list.currentRow()
        if row < 0 or len(self._templates) <= 1:
            return
        self._templates.pop(row)
        self._populate_list()
        self._list.setCurrentRow(min(row, len(self._templates) - 1))

    def templates(self) -> list[dict]:
        return self._templates
