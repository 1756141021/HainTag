from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..models import PromptEntry
from ..ui_tokens import (
    CLS_FIELD_COMBO,
    CLS_FIELD_INPUT,
    CLS_FIELD_LABEL,
    CLS_FIELD_SPIN,
    CLS_PROMPT_DELETE_BUTTON,
    CLS_PROMPT_DRAG_HANDLE,
    CLS_PROMPT_ENTRY_BODY,
    CLS_PROMPT_ENTRY_FRAME,
    CLS_PROMPT_ENTRY_HEADER,
    CLS_PROMPT_EXPAND_INDICATOR,
    CLS_PROMPT_NAME_PREVIEW,
    CLS_PROMPT_TEXT,
    _dp,
)
from .common import DragHandleLabel, ToggleSwitch


class PromptEntryWidget(QFrame):
    changed = pyqtSignal()
    delete_requested = pyqtSignal(object)
    drag_requested = pyqtSignal(object)
    size_hint_changed = pyqtSignal()

    _MIN_BODY_HEIGHT = 104
    _MAX_BODY_HEIGHT = 240

    def __init__(self, translator: Translator, entry: PromptEntry, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._expanded = False
        self._current_body_height = 0
        self.setProperty("class", CLS_PROMPT_ENTRY_FRAME)
        self.setProperty("expanded", False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QWidget(self)
        self.header.setProperty("class", CLS_PROMPT_ENTRY_HEADER)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(_dp(8), _dp(5), _dp(8), _dp(5))
        header_layout.setSpacing(_dp(5))

        self.order_spin = QSpinBox(self.header)
        self.order_spin.setMinimum(0)
        self.order_spin.setMaximum(9999)
        self.order_spin.setProperty("class", CLS_FIELD_SPIN)
        self.order_spin.setFixedWidth(_dp(58))
        self.order_spin.setToolTip(translator.t("tip_order"))
        header_layout.addWidget(self.order_spin)

        self.drag_handle = DragHandleLabel(parent=self.header)
        self.drag_handle.setProperty("class", CLS_PROMPT_DRAG_HANDLE)
        self.drag_handle.drag_started.connect(lambda: self.drag_requested.emit(self))
        header_layout.addWidget(self.drag_handle)

        self.enabled_toggle = ToggleSwitch(self.header)
        header_layout.addWidget(self.enabled_toggle)

        self.name_host = QWidget(self.header)
        self.name_stack = QStackedLayout(self.name_host)
        self.name_stack.setContentsMargins(0, 0, 0, 0)
        self.name_stack.setSpacing(0)

        self.name_preview = QLabel(self.name_host)
        self.name_preview.setProperty("class", CLS_PROMPT_NAME_PREVIEW)
        self.name_preview.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.name_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.name_stack.addWidget(self.name_preview)

        self.name_edit = QLineEdit(self.name_host)
        self.name_edit.setProperty("class", CLS_FIELD_INPUT)
        self.name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.name_stack.addWidget(self.name_edit)
        header_layout.addWidget(self.name_host, 1)

        self.role_combo = QComboBox(self.header)
        self.role_combo.setProperty("class", CLS_FIELD_COMBO)
        self.role_combo.setMinimumWidth(_dp(82))
        header_layout.addWidget(self.role_combo)

        self.depth_label = QLabel(self.header)
        self.depth_label.setProperty("class", CLS_FIELD_LABEL)
        header_layout.addWidget(self.depth_label)

        self.depth_spin = QSpinBox(self.header)
        self.depth_spin.setMinimum(0)
        self.depth_spin.setMaximum(999)
        self.depth_spin.setProperty("class", CLS_FIELD_SPIN)
        self.depth_spin.setFixedWidth(_dp(58))
        self.depth_spin.setToolTip(translator.t("tip_depth"))
        header_layout.addWidget(self.depth_spin)

        self.expand_indicator = QLabel(self.header)
        self.expand_indicator.setProperty("class", CLS_PROMPT_EXPAND_INDICATOR)
        self.expand_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.expand_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout.addWidget(self.expand_indicator)

        self.delete_button = QPushButton("×", self.header)
        self.delete_button.setProperty("class", CLS_PROMPT_DELETE_BUTTON)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self))
        header_layout.addWidget(self.delete_button)

        root.addWidget(self.header)

        self.body = QWidget(self)
        self.body.setProperty("class", CLS_PROMPT_ENTRY_BODY)
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(_dp(8), 0, _dp(8), _dp(8))
        body_layout.setSpacing(0)

        self.content_edit = QTextEdit(self.body)
        self.content_edit.setProperty("class", CLS_PROMPT_TEXT)
        self.content_edit.setMinimumHeight(_dp(self._MIN_BODY_HEIGHT))
        self.content_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        body_layout.addWidget(self.content_edit)
        root.addWidget(self.body)
        self.body.hide()
        self.body.setMaximumHeight(0)

        self._animation = QPropertyAnimation(self.body, b"maximumHeight", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_animation_value_changed)
        self._animation.finished.connect(self._on_animation_finished)

        self._interactive_widgets = [
            self.order_spin,
            self.drag_handle,
            self.enabled_toggle,
            self.name_edit,
            self.role_combo,
            self.depth_spin,
            self.delete_button,
        ]

        for widget in [self.order_spin, self.name_edit, self.depth_spin, self.content_edit]:
            if isinstance(widget, QTextEdit):
                widget.textChanged.connect(self.changed)
            else:
                widget.textChanged.connect(self.changed)
        self.name_edit.textChanged.connect(self._sync_name_preview)
        self.role_combo.currentIndexChanged.connect(self.changed)
        self.enabled_toggle.toggled.connect(self.changed)
        document_layout = self.content_edit.document().documentLayout()
        if document_layout is not None:
            document_layout.documentSizeChanged.connect(lambda *_: self._refresh_body_height())

        for widget in (self.header, self.name_host, self.name_preview, self.expand_indicator):
            widget.installEventFilter(self)
        self.set_entry(entry)
        self.set_expanded(False)

    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(watched, event)
        if watched is self.header:
            self._handle_header_press(event)
            return True
        if watched in (self.name_host, self.name_preview, self.expand_indicator):
            self._toggle_from_header_widget(event)
            return True
        return super().eventFilter(watched, event)

    def _handle_header_press(self, event) -> None:
        child = self.header.childAt(event.position().toPoint())
        while child is not None and child is not self.header:
            if child in self._interactive_widgets:
                return
            child = child.parentWidget()
        self.set_expanded(not self._expanded)

    def _toggle_from_header_widget(self, event) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        target_height = self._expanded_body_height() if expanded else 0
        if self._expanded == expanded and self._current_body_height == target_height:
            return
        self._expanded = expanded
        self.name_stack.setCurrentWidget(self.name_edit if expanded else self.name_preview)
        self.setProperty("expanded", expanded)
        self._update_indicator()
        self.style().unpolish(self)
        self.style().polish(self)
        self._animation.stop()
        start_height = self._current_body_height
        if expanded:
            self.body.show()
        self._animation.setStartValue(start_height)
        self._animation.setEndValue(target_height)
        if start_height == target_height:
            self._on_animation_value_changed(target_height)
            self._on_animation_finished()
            return
        self._animation.start()

    def set_entry(self, entry: PromptEntry) -> None:
        self.order_spin.setValue(entry.order)
        self.enabled_toggle.setChecked(entry.enabled)
        self.name_edit.setText(entry.name)
        self.depth_spin.setValue(entry.depth)
        self.content_edit.setPlainText(entry.content)
        self.retranslate_ui()
        self._sync_name_preview()
        role_index = max(0, self.role_combo.findData(entry.role))
        self.role_combo.setCurrentIndex(role_index)
        self._refresh_body_height()

    def entry(self) -> PromptEntry:
        return PromptEntry(
            name=self.name_edit.text().strip() or "Main Prompt",
            role=str(self.role_combo.currentData()),
            depth=int(self.depth_spin.value()),
            order=int(self.order_spin.value()),
            enabled=self.enabled_toggle.isChecked(),
            content=self.content_edit.toPlainText(),
        )

    def retranslate_ui(self) -> None:
        current_role = self.role_combo.currentData()
        self.role_combo.blockSignals(True)
        self.role_combo.clear()
        self.role_combo.addItem(self._translator.t("role_system"), "system")
        self.role_combo.addItem(self._translator.t("role_user"), "user")
        self.role_combo.addItem(self._translator.t("role_assistant"), "assistant")
        role_index = max(0, self.role_combo.findData(current_role or "system"))
        self.role_combo.setCurrentIndex(role_index)
        self.role_combo.blockSignals(False)
        self.depth_label.setText(self._translator.t("depth"))
        self.order_spin.setToolTip(self._translator.t("order"))
        self.delete_button.setToolTip(self._translator.t("delete"))
        self.content_edit.setPlaceholderText(self._translator.t("prompt_placeholder"))
        self._update_indicator()
        self._sync_name_preview()
        self._refresh_body_height()

    def sizeHint(self) -> QSize:
        return QSize(max(self.header.sizeHint().width(), 320), self.header.sizeHint().height() + self._current_body_height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_body_height()

    def _refresh_body_height(self) -> None:
        if not self._expanded:
            return
        target_height = self._expanded_body_height()
        if self._animation.state() == QAbstractAnimation.State.Running:
            self._animation.setEndValue(target_height)
            return
        self.body.show()
        self.body.setMaximumHeight(target_height)
        self._on_animation_value_changed(target_height)

    def _expanded_body_height(self) -> int:
        layout = self.body.layout()
        margins = layout.contentsMargins() if layout is not None else self.contentsMargins()
        document_height = int(round(self.content_edit.document().size().height()))
        frame_height = self.content_edit.frameWidth() * 2
        padding_height = margins.top() + margins.bottom() + 20
        return max(_dp(self._MIN_BODY_HEIGHT), min(_dp(self._MAX_BODY_HEIGHT), document_height + frame_height + padding_height))

    def _on_animation_value_changed(self, value) -> None:
        self._current_body_height = max(0, int(value))
        self.updateGeometry()
        self.size_hint_changed.emit()

    def _on_animation_finished(self) -> None:
        if not self._expanded:
            self.body.hide()
            self.body.setMaximumHeight(0)
            self._current_body_height = 0
            self.updateGeometry()
            self.size_hint_changed.emit()

    def _update_indicator(self) -> None:
        self.expand_indicator.setText("⌃" if self._expanded else "⌄")

    def _sync_name_preview(self) -> None:
        preview = self.name_edit.text().strip() or self._translator.t("new_prompt")
        self.name_preview.setText(preview)


class PromptListWidget(QListWidget):
    changed = pyqtSignal()

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSpacing(_dp(4))
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setUniformItemSizes(False)
        self.model().rowsMoved.connect(self._on_rows_moved)

    def add_entry(self, entry: PromptEntry, *, expanded: bool = False) -> PromptEntryWidget:
        item = QListWidgetItem(self)
        widget = PromptEntryWidget(self._translator, entry, self)
        item.setSizeHint(widget.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, widget)
        widget.changed.connect(lambda: self._sync_widget_size_hint(widget))
        widget.changed.connect(self.changed)
        widget.delete_requested.connect(self.remove_entry_widget)
        widget.drag_requested.connect(self.start_drag_for_widget)
        widget.size_hint_changed.connect(lambda: self._sync_widget_size_hint(widget))
        if expanded:
            widget.set_expanded(True)
            self._sync_widget_size_hint(widget)
        return widget

    def remove_entry_widget(self, widget: PromptEntryWidget) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if self.itemWidget(item) is widget:
                self.takeItem(row)
                widget.deleteLater()
                self.changed.emit()
                return

    def start_drag_for_widget(self, widget: PromptEntryWidget) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if self.itemWidget(item) is widget:
                self.setCurrentRow(row)
                self.startDrag(Qt.DropAction.MoveAction)
                return

    def entries(self) -> list[PromptEntry]:
        result: list[PromptEntry] = []
        for row in range(self.count()):
            widget = self.itemWidget(self.item(row))
            if isinstance(widget, PromptEntryWidget):
                result.append(widget.entry())
        return result

    def replace_entries(self, entries: list[PromptEntry]) -> None:
        self.clear()
        for entry in entries:
            self.add_entry(entry, expanded=False)
        self._sync_size_hints()
        self.changed.emit()

    def retranslate_ui(self) -> None:
        for row in range(self.count()):
            widget = self.itemWidget(self.item(row))
            if isinstance(widget, PromptEntryWidget):
                widget.retranslate_ui()
                self.item(row).setSizeHint(widget.sizeHint())
        self.doItemsLayout()
        self.viewport().update()

    def _sync_size_hints(self) -> None:
        for row in range(self.count()):
            widget = self.itemWidget(self.item(row))
            if widget is not None:
                self.item(row).setSizeHint(widget.sizeHint())
        self.doItemsLayout()
        self.viewport().update()

    def _sync_widget_size_hint(self, widget: PromptEntryWidget) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if self.itemWidget(item) is widget:
                item.setSizeHint(widget.sizeHint())
                break
        self.doItemsLayout()
        self.viewport().update()

    def _on_rows_moved(self, *_args) -> None:
        self._sync_size_hints()
        self.changed.emit()


class PromptManagerWidget(QWidget):
    changed = pyqtSignal()
    preview_requested = pyqtSignal()

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(_dp(8))

        self.list_widget = PromptListWidget(translator, self)
        self.list_widget.changed.connect(self.changed)
        root.addWidget(self.list_widget, 1)

        # Bottom row: add button + preview button
        btn_row = QHBoxLayout()
        btn_row.setSpacing(_dp(6))
        self.add_button = QPushButton(self)
        self.add_button.setObjectName("GhostButton")
        self.add_button.clicked.connect(self._add_prompt)
        btn_row.addWidget(self.add_button)
        btn_row.addStretch()
        self.preview_button = QPushButton("⋯", self)
        self.preview_button.setObjectName("GhostButton")
        self.preview_button.setFixedWidth(_dp(32))
        self.preview_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_button.clicked.connect(self.preview_requested.emit)
        btn_row.addWidget(self.preview_button)
        root.addLayout(btn_row)
        self.retranslate_ui()

    def _add_prompt(self) -> None:
        next_order = max([entry.order for entry in self.prompt_entries()] or [0]) + 1
        widget = self.list_widget.add_entry(
            PromptEntry(name=self._translator.t("new_prompt"), order=next_order, role="system", depth=0),
            expanded=True,
        )
        widget.content_edit.setFocus()
        self.changed.emit()

    def prompt_entries(self) -> list[PromptEntry]:
        return self.list_widget.entries()

    def set_prompt_entries(self, entries: list[PromptEntry]) -> None:
        self.list_widget.replace_entries(entries)

    def retranslate_ui(self) -> None:
        self.add_button.setText(self._translator.t("add_prompt"))
        self.preview_button.setToolTip(self._translator.t("prompt_preview"))
        self.list_widget.retranslate_ui()


