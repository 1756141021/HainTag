from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..theme import _fs, current_palette
from ..ui_tokens import _dp


class CollapsibleSection(QWidget):
    """A section with a clickable header that toggles content visibility.

    Reusable anywhere a collapsible panel is needed (metadata viewer,
    settings, etc.).
    """

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        content: QWidget,
        *,
        collapsed: bool = False,
        right_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._content = content
        self._collapsed = collapsed

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # Header row
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(_dp(4))

        self._toggle_btn = QPushButton(self)
        self._toggle_btn.setFixedSize(_dp(20), _dp(20))
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.clicked.connect(self.toggle)
        header.addWidget(self._toggle_btn)

        self._title_label = QLabel(title, self)
        self._title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_label.mousePressEvent = lambda _: self.toggle()
        header.addWidget(self._title_label, 1)

        if right_widget is not None:
            header.addWidget(right_widget)

        root.addLayout(header)
        root.addWidget(content)

        self._update_state()
        self.apply_theme()

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._update_state()
        self.toggled.emit(self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed != collapsed:
            self._collapsed = collapsed
            self._update_state()

    def _update_state(self) -> None:
        self._content.setVisible(not self._collapsed)
        self._toggle_btn.setText("▶" if self._collapsed else "▼")

    def apply_theme(self) -> None:
        pal = current_palette()
        accent = pal['accent_text']
        self._toggle_btn.setFixedSize(_dp(20), _dp(20))
        self._toggle_btn.setStyleSheet(f"color: {accent}; border: none; font-size: {_fs('fs_10')};")
        self._title_label.setStyleSheet(
            f"color: {accent}; font-weight: bold; font-size: {_fs('fs_13')};"
        )
