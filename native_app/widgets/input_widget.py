from __future__ import annotations

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from ..i18n import Translator
from ..theme import is_theme_light
from ..ui_tokens import CLS_FIELD_LABEL, CLS_INPUT_EDITOR, INPUT_ACTION_BUTTON


class InputWidget(QWidget):
    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._sending = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.editor = QTextEdit(self)
        self.editor.setProperty('class', CLS_INPUT_EDITOR)
        root.addWidget(self.editor, 1)

        self.action_bar = QWidget(self)
        self.action_bar.setObjectName('InputActionBar')
        footer = QHBoxLayout(self.action_bar)
        footer.setContentsMargins(10, 6, 10, 10)
        footer.setSpacing(6)

        self.token_label = QLabel(self.action_bar)
        self.token_label.setObjectName('TokenLabel')
        self.token_label.setProperty('class', CLS_FIELD_LABEL)
        footer.addWidget(self.token_label)
        footer.addStretch(1)

        self.summary_button = QPushButton(self.action_bar)
        self.summary_button.setObjectName('SecondaryIconButton')
        self.summary_button.setFixedSize(INPUT_ACTION_BUTTON, INPUT_ACTION_BUTTON)
        footer.addWidget(self.summary_button)

        self.send_button = QPushButton(self.action_bar)
        self.send_button.setObjectName('PrimaryIconButton')
        self.send_button.setFixedSize(INPUT_ACTION_BUTTON, INPUT_ACTION_BUTTON)
        footer.addWidget(self.send_button)

        root.addWidget(self.action_bar, 0)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.editor.setPlaceholderText(self._translator.t('input_placeholder'))
        self.summary_button.setText('Σ')
        self.summary_button.setToolTip(self._translator.t('summary'))
        self.send_button.setText('■' if self._sending else '➤')
        self.send_button.setToolTip(self._translator.t('stop') if self._sending else self._translator.t('send'))
        if not self.token_label.text():
            self.token_label.setText(f"~0 / 2048 {self._translator.t('token_count')}")

    def set_sending(self, sending: bool) -> None:
        self._sending = sending
        self.summary_button.setEnabled(not sending)
        self.retranslate_ui()

    def set_text(self, value: str) -> None:
        self.editor.blockSignals(True)
        self.editor.setPlainText(value)
        self.editor.blockSignals(False)

    def text(self) -> str:
        return self.editor.toPlainText()

    def clear_text(self) -> None:
        self.editor.clear()

    def append_separator(self) -> None:
        current = self.editor.toPlainText()
        suffix = '\n\n---\n'
        if current and not current.endswith(suffix):
            self.editor.moveCursor(QTextCursor.MoveOperation.End)
            self.editor.insertPlainText(suffix)
        elif not current:
            self.editor.setPlainText('---\n')

    def append_text(self, value: str) -> None:
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.insertPlainText(value)
        self.editor.ensureCursorVisible()

    def append_status_line(self, value: str) -> None:
        text = self.editor.toPlainText()
        suffix = value if text.endswith('\n') or not text else f'\n{value}'
        self.append_text(suffix)

    def set_token_estimate(self, estimated_tokens: int, max_tokens: int) -> None:
        self.token_label.setText(f"~{estimated_tokens} / {max_tokens} {self._translator.t('token_count')}")
        ratio = (estimated_tokens / max_tokens) if max_tokens else 0.0
        light = is_theme_light()
        if ratio > 0.95:
            color = '#cc4444' if light else '#ff7676'
        elif ratio > 0.8:
            color = '#cc8800' if light else '#ffcc66'
        else:
            color = None
        self.token_label.setStyleSheet(f'color: {color};' if color else '')
