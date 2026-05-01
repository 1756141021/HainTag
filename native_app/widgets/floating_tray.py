"""Floating tray for storing overlapping floating cards."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from ..i18n import Translator
from ..models import FloatingTrayMemberState, FloatingTrayState
from ..theme import _fs, current_palette
from ..ui_tokens import _dp
from .text_context_menu import apply_app_menu_style


class FloatingTrayWidget(QWidget):
    member_requested = pyqtSignal(str)
    position_changed = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("FloatingTray")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.mapToGlobal(pos))
        )
        self._translator = translator
        self._members: list[FloatingTrayMemberState] = []
        self._labels: dict[str, str] = {}
        self._member_buttons: dict[str, QPushButton] = {}
        self._active_widget_id = ""
        self._batch_depth = 0
        self._rebuild_pending = False
        self._dragging = False
        self._drag_offset = QPoint()
        self._drag_start_global = QPoint()
        self._drag_moved = False

        root = QVBoxLayout(self)
        root.setContentsMargins(_dp(6), _dp(6), _dp(6), _dp(6))
        root.setSpacing(_dp(4))

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(_dp(4))

        self._title = QLabel(self)
        self._title.setCursor(Qt.CursorShape.OpenHandCursor)
        self._title.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._title.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self._title.mapToGlobal(pos))
        )
        self._title.installEventFilter(self)
        title_row.addWidget(self._title, 1)

        self._close_btn = QPushButton("×", self)
        self._close_btn.setObjectName("FloatingTrayClose")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFixedSize(_dp(18), _dp(18))
        self._close_btn.clicked.connect(self.close_requested.emit)
        title_row.addWidget(self._close_btn)
        root.addLayout(title_row)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(_dp(3))
        root.addLayout(self._body)

        self.setMinimumWidth(_dp(112))
        self.setMaximumWidth(_dp(160))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.hide()
        self.apply_theme()

    def set_labels(self, labels: dict[str, str]) -> None:
        self._labels = dict(labels)
        self._rebuild()

    def member_ids(self) -> list[str]:
        return [member.widget_id for member in self._members]

    def member_states(self) -> list[FloatingTrayMemberState]:
        return list(self._members)

    def should_show(self) -> bool:
        return len(self._members) > 1

    def begin_batch_update(self) -> None:
        self._batch_depth += 1

    def end_batch_update(self) -> None:
        self._batch_depth = max(0, self._batch_depth - 1)
        if self._batch_depth == 0 and self._rebuild_pending:
            self._rebuild_pending = False
            self._rebuild()

    def member_state(self, widget_id: str) -> FloatingTrayMemberState | None:
        for member in self._members:
            if member.widget_id == widget_id:
                return member
        return None

    def set_active_member(self, widget_id: str) -> None:
        self._active_widget_id = widget_id if self.has_member(widget_id) else ""
        self._refresh_active_buttons()

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
                if self._active_widget_id == widget_id:
                    self._active_widget_id = ""
                self._rebuild()
                return removed
        return None

    def clear_members(self) -> None:
        self._members.clear()
        self._active_widget_id = ""
        self._rebuild()

    def tray_state(self) -> FloatingTrayState:
        if self.isVisible() and self.should_show():
            self.ensure_visible()
        should_persist = self.isVisible() and self.should_show()
        return FloatingTrayState(
            visible=should_persist,
            x=self.x(),
            y=self.y(),
            members=list(self._members) if should_persist else [],
        )

    def restore_state(self, state: FloatingTrayState) -> None:
        self._members = list(state.members)
        self.move(state.x, state.y)
        self._rebuild()
        if state.visible and self.should_show():
            self.show()
            self.ensure_visible()
        else:
            self.hide()

    def ensure_visible(self) -> None:
        """Keep the tray recoverable when saved monitor geometry changes."""
        target = self._clamped_position(self.pos())
        if target != self.pos():
            self.move(target)

    def retranslate_ui(self) -> None:
        self._title.setText(self._title_text())
        self._title.setToolTip(self._translator.t("floating_tray_hint"))
        self._close_btn.setToolTip(self._translator.t("floating_tray_close"))
        for member in self._members:
            button = self._member_buttons.get(member.widget_id)
            if button is not None:
                button.setText(self._member_text(member))
                button.setToolTip(self._member_tooltip(member))
        self.apply_theme()

    def _rebuild(self) -> None:
        if self._batch_depth > 0:
            self._rebuild_pending = True
            return

        self._member_buttons.clear()
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for member in self._members:
            button = QPushButton(self._member_text(member), self)
            button.setObjectName("FloatingTrayMember")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("active", member.widget_id == self._active_widget_id)
            button.setToolTip(self._member_tooltip(member))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, b=button: self._show_context_menu(b.mapToGlobal(pos))
            )
            button.clicked.connect(lambda _checked=False, widget_id=member.widget_id: self.member_requested.emit(widget_id))
            self._member_buttons[member.widget_id] = button
            self._body.addWidget(button)

        self._title.setText(self._title_text())
        self._title.setToolTip(self._translator.t("floating_tray_hint"))
        self.setVisible(self.should_show())
        self.adjustSize()
        if self.isVisible():
            self.ensure_visible()
        self.apply_theme()

    def apply_theme(self) -> None:
        p = current_palette()
        root = self.layout()
        if root is not None:
            root.setContentsMargins(_dp(6), _dp(6), _dp(6), _dp(6))
            root.setSpacing(_dp(4))
        self._body.setSpacing(_dp(3))
        self.setMinimumWidth(_dp(112))
        self.setMaximumWidth(_dp(160))
        self.setStyleSheet(
            f"#FloatingTray {{ background: {p['bg_surface']}; border: 1px solid {p['line_strong']}; border-radius: {_dp(7)}px; }}"
            f" QLabel {{ color: {p['text']}; font-size: {_fs('fs_10')}; }}"
            f" QPushButton#FloatingTrayClose {{ color: {p['text_dim']}; background: transparent; border: none; border-radius: {_dp(2)}px; font-size: {_fs('fs_11')}; }}"
            f" QPushButton#FloatingTrayClose:hover {{ color: {p['text']}; background: {p['hover_bg_strong']}; }}"
            f" QPushButton#FloatingTrayMember {{ color: {p['text']}; background: {p['bg_content']}; border: 1px solid {p['line']}; border-radius: {_dp(3)}px; padding: {_dp(4)}px {_dp(6)}px; font-size: {_fs('fs_9')}; text-align: left; }}"
            f" QPushButton#FloatingTrayMember:hover {{ background: {p['hover_bg']}; border-color: {p['line_strong']}; color: {p['text']}; }}"
            f" QPushButton#FloatingTrayMember:pressed {{ background: {p['accent']}; color: {p['accent_text']}; border-color: {p['accent']}; }}"
            f" QPushButton#FloatingTrayMember[active=\"true\"] {{ background: {p['accent_sub']}; border-color: {p['accent_hover']}; color: {p['accent_text']}; }}"
        )
        self._title.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; font-weight: bold;"
        )
        self._close_btn.setFixedSize(_dp(18), _dp(18))
        self._refresh_active_buttons()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._title and self._handle_drag_event(event):
            return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:
        if self._handle_drag_event(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._handle_drag_event(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._handle_drag_event(event):
            return
        super().mouseReleaseEvent(event)

    def _handle_drag_event(self, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            self._dragging = True
            self._drag_moved = False
            self._drag_start_global = global_pos
            self._drag_offset = global_pos - self.pos()
            self._title.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return True
        if event_type == QEvent.Type.MouseMove and self._dragging:
            global_pos = event.globalPosition().toPoint()
            if (global_pos - self._drag_start_global).manhattanLength() > _dp(3):
                self._drag_moved = True
            self.move(self._clamped_position(global_pos - self._drag_offset))
            event.accept()
            return True
        if event_type == QEvent.Type.MouseButtonRelease and self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.ensure_visible()
            self._title.setCursor(Qt.CursorShape.OpenHandCursor)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if self._drag_moved:
                self.position_changed.emit()
            elif self._members:
                self.member_requested.emit(self._members[0].widget_id)
            event.accept()
            return True
        return False

    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        apply_app_menu_style(menu)
        close_action = menu.addAction(self._translator.t("floating_tray_close"))
        chosen = menu.exec(global_pos)
        if chosen is close_action:
            self.close_requested.emit()

    def _title_text(self) -> str:
        return f"{self._translator.t('floating_tray')} · {len(self._members)}"

    def _member_label(self, member: FloatingTrayMemberState) -> str:
        return self._labels.get(member.widget_id, member.widget_id)

    def _member_text(self, member: FloatingTrayMemberState) -> str:
        label = self._member_label(member)
        try:
            index = self.member_ids().index(member.widget_id) + 1
        except ValueError:
            index = 1
        available_width = max(_dp(56), self.maximumWidth() - _dp(44))
        elided = self.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, available_width)
        return f"{index}  {elided}"

    def _member_tooltip(self, member: FloatingTrayMemberState) -> str:
        label = self._labels.get(member.widget_id, member.widget_id)
        return f"{label}\n{self._translator.t('floating_tray_show')}"

    def _refresh_active_buttons(self) -> None:
        for widget_id, button in self._member_buttons.items():
            button.setProperty("active", widget_id == self._active_widget_id)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _screen_geometry_for(self, pos: QPoint) -> QRect:
        center = pos + QPoint(max(1, self.width()) // 2, max(1, self.height()) // 2)
        screen = QGuiApplication.screenAt(center) or QGuiApplication.screenAt(pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1280, 800)
        return screen.geometry()

    def _clamped_position(self, pos: QPoint) -> QPoint:
        available = self._screen_geometry_for(pos)
        grab = _dp(36)
        width = max(self.width(), self.sizeHint().width(), self.minimumWidth(), _dp(120))
        height = max(self.height(), self.sizeHint().height(), _dp(80))
        min_x = available.left() - width + grab
        min_y = available.top() - height + grab
        max_x = available.right() - grab
        max_y = available.bottom() - grab
        return QPoint(
            max(min_x, min(pos.x(), max_x)),
            max(min_y, min(pos.y(), max_y)),
        )
