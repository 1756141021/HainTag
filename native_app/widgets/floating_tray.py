"""Floating tray for storing overlapping floating cards."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..i18n import Translator
from ..models import FloatingTrayMemberState, FloatingTrayState
from ..theme import _fs, current_palette
from ..ui_tokens import _dp


class FloatingTrayWidget(QWidget):
    member_requested = pyqtSignal(str)

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("FloatingTray")
        self._translator = translator
        self._members: list[FloatingTrayMemberState] = []
        self._labels: dict[str, str] = {}
        self._member_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(_dp(8), _dp(8), _dp(8), _dp(8))
        root.setSpacing(_dp(6))

        self._title = QLabel(self)
        root.addWidget(self._title)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(_dp(4))
        root.addLayout(self._body)

        self.setMinimumWidth(_dp(180))
        self.hide()
        self.apply_theme()

    def set_labels(self, labels: dict[str, str]) -> None:
        self._labels = dict(labels)
        self._rebuild()

    def member_ids(self) -> list[str]:
        return [member.widget_id for member in self._members]

    def has_member(self, widget_id: str) -> bool:
        return any(member.widget_id == widget_id for member in self._members)

    def add_member(self, member: FloatingTrayMemberState) -> None:
        if self.has_member(member.widget_id):
            self.update_member(member)
            return
        self._members.append(member)
        self._rebuild()

    def update_member(self, member: FloatingTrayMemberState) -> None:
        for index, existing in enumerate(self._members):
            if existing.widget_id == member.widget_id:
                self._members[index] = member
                break
        else:
            self._members.append(member)
        self._rebuild()

    def remove_member(self, widget_id: str) -> FloatingTrayMemberState | None:
        for index, member in enumerate(self._members):
            if member.widget_id == widget_id:
                removed = self._members.pop(index)
                self._rebuild()
                return removed
        return None

    def clear_members(self) -> None:
        self._members.clear()
        self._rebuild()

    def tray_state(self) -> FloatingTrayState:
        return FloatingTrayState(
            visible=self.isVisible() and bool(self._members),
            x=self.x(),
            y=self.y(),
            members=list(self._members),
        )

    def restore_state(self, state: FloatingTrayState) -> None:
        self._members = list(state.members)
        self.move(state.x, state.y)
        self._rebuild()
        if state.visible and self._members:
            self.show()

    def retranslate_ui(self) -> None:
        self._title.setText(f"{self._translator.t('floating_tray')} ({len(self._members)})")
        for button in self._member_buttons.values():
            button.setText(self._translator.t("restore"))
        self.apply_theme()

    def _rebuild(self) -> None:
        self._member_buttons.clear()
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for member in self._members:
            row = QWidget(self)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(_dp(6))
            label = QLabel(self._labels.get(member.widget_id, member.widget_id), row)
            layout.addWidget(label)
            layout.addStretch()
            button = QPushButton(self._translator.t("restore"), row)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, widget_id=member.widget_id: self.member_requested.emit(widget_id))
            layout.addWidget(button)
            self._member_buttons[member.widget_id] = button
            self._body.addWidget(row)

        self._title.setText(f"{self._translator.t('floating_tray')} ({len(self._members)})")
        self.setVisible(bool(self._members))
        self.adjustSize()
        self.apply_theme()

    def apply_theme(self) -> None:
        p = current_palette()
        self.setStyleSheet(
            f"#FloatingTray {{ background: {p['bg_surface']}; border: 1px solid {p['line_strong']}; border-radius: 8px; }}"
            f" QLabel {{ color: {p['text']}; font-size: {_fs('fs_10')}; }}"
            f" QPushButton {{ color: {p['text']}; background: {p['accent']}; border: none; border-radius: 4px; padding: 2px 8px; font-size: {_fs('fs_10')}; }}"
        )
        self._title.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; font-weight: bold;"
        )
