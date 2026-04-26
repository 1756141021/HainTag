from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QBoxLayout, QFrame, QMenu, QPushButton, QWidget

from ..models import DockPosition, DockState
from .common import compute_resized_rect
from ..ui_tokens import (
    DOCK_COLLAPSED_MAX_SIDE,
    DOCK_COLLAPSED_MAX_TOP,
    DOCK_COLLAPSED_MIN,
    DOCK_COLLAPSED_THICKNESS,
    DOCK_CORNER_HOTZONE,
    DOCK_EDGE_HOTZONE,
    DOCK_EXPANDED_SIDE,
    DOCK_EXPANDED_SIDE_MAX,
    DOCK_EXPANDED_SIDE_MIN,
    DOCK_EXPANDED_TOP,
    DOCK_EXPANDED_TOP_MAX,
    DOCK_EXPANDED_TOP_MIN,
    DOCK_FLOAT_CORNER_HOTZONE,
    DOCK_FLOAT_EDGE_HOTZONE,
    DOCK_FLOAT_HEIGHT,
    DOCK_FLOAT_MIN_HEIGHT,
    DOCK_FLOAT_MIN_WIDTH,
    DOCK_FLOAT_RESIZE_HINT,
    DOCK_FLOAT_WIDTH,
    CLS_DOCK_ITEM_BUTTON,
)


class DockItemButton(QPushButton):
    activated = pyqtSignal(str)
    dragged_out = pyqtSignal(str, QPoint)
    close_requested = pyqtSignal(str)

    def __init__(self, widget_id: str, icon_text: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.icon_text = icon_text
        self.label_text = label
        self.setProperty('class', CLS_DOCK_ITEM_BUTTON)
        self._press_pos = QPoint()
        self._dragging = False
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.refresh_text(False, False)

    def refresh_text(self, expanded: bool, floating: bool) -> None:
        self.setText(f'{self.icon_text}  {self.label_text}' if expanded or floating else self.icon_text)

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        close_action = menu.addAction(self._close_label or '关闭')
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is close_action:
            self.close_requested.emit(self.widget_id)

    def set_close_label(self, label: str) -> None:
        self._close_label = label

    _close_label: str = ''

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            if (event.globalPosition().toPoint() - self._press_pos).manhattanLength() >= 6:
                self._dragging = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            if self._dragging:
                parent = self.parentWidget()
                if parent is not None:
                    local = parent.mapFromGlobal(global_pos)
                    if not parent.rect().contains(local):
                        self.dragged_out.emit(self.widget_id, global_pos)
                    else:
                        self.activated.emit(self.widget_id)
                else:
                    self.dragged_out.emit(self.widget_id, global_pos)
            else:
                self.activated.emit(self.widget_id)
        self._dragging = False
        super().mouseReleaseEvent(event)


class DockPanel(QFrame):
    state_changed = pyqtSignal()
    preview_changed = pyqtSignal(str)
    widget_activated = pyqtSignal(str)
    widget_drag_restored = pyqtSignal(str, QPoint)
    widget_close_requested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName('DockPanel')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self._state = DockState(
            collapsed_thickness=DOCK_COLLAPSED_THICKNESS,
            expanded_vertical_size=DOCK_EXPANDED_SIDE,
            expanded_horizontal_size=DOCK_EXPANDED_TOP,
            floating_width=DOCK_FLOAT_WIDTH,
            floating_height=DOCK_FLOAT_HEIGHT,
        )
        self._container_rect_provider: Callable[[], QRect] | None = None
        self._drag_pending = False
        self._dragging = False
        self._drag_origin = QPoint()
        self._drag_offset = QPoint()
        self._resize_edge = False
        self._resize_origin = QPoint()
        self._size_origin = 0
        self._resize_started_collapsed = False
        self._resize_floating = False
        self._resize_floating_direction = ''
        self._float_rect_origin = QRect()

        self.root_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.root_layout.setContentsMargins(6, 8, 6, 8)
        self.root_layout.setSpacing(6)

        self.toggle_button = QPushButton('‹', self)
        self.toggle_button.setObjectName('DockToggle')
        self.toggle_button.clicked.connect(self.toggle_expanded)
        self.root_layout.addWidget(self.toggle_button)

        self.items_container = QWidget(self)
        self.items_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(4)
        self.root_layout.addWidget(self.items_container, 1)

        self.edge_handle = QFrame(self)
        self.edge_handle.setObjectName('DockEdgeHandle')
        self.edge_handle.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.edge_handle.setCursor(Qt.CursorShape.SizeHorCursor)
        self.edge_handle.installEventFilter(self)

        self.corner_handle = QFrame(self)
        self.corner_handle.setObjectName('DockCornerHandle')
        self.corner_handle.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.corner_handle.setProperty('resizeDirection', 'bottom_right')
        self.corner_handle.setProperty('visualHint', True)
        self.corner_handle.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.corner_handle.installEventFilter(self)

        self._floating_resize_handles: dict[str, QFrame] = {}
        for direction, cursor in {
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'top_left': Qt.CursorShape.SizeFDiagCursor,
            'top_right': Qt.CursorShape.SizeBDiagCursor,
            'bottom_left': Qt.CursorShape.SizeBDiagCursor,
        }.items():
            handle = QFrame(self)
            handle.setObjectName('DockCornerHandle' if '_' in direction else 'DockEdgeHandle')
            handle.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            handle.setProperty('resizeDirection', direction)
            handle.setCursor(cursor)
            handle.installEventFilter(self)
            self._floating_resize_handles[direction] = handle

        self._items: dict[str, DockItemButton] = {}
        self._refresh_layout_direction()

    _close_label: str = ''

    def set_close_label(self, label: str) -> None:
        self._close_label = label
        for button in self._items.values():
            button.set_close_label(label)

    def apply_theme(self) -> None:
        for widget in [self, self.toggle_button, self.items_container, self.edge_handle, self.corner_handle]:
            self.style().unpolish(widget)
            self.style().polish(widget)
        for handle in self._floating_resize_handles.values():
            self.style().unpolish(handle)
            self.style().polish(handle)
        for button in self._items.values():
            self.style().unpolish(button)
            self.style().polish(button)

    def set_container_rect_provider(self, provider: Callable[[], QRect]) -> None:
        self._container_rect_provider = provider

    def set_state(self, state: DockState) -> None:
        self._state = state
        self._normalize_state()
        self._refresh_layout_direction()
        self._refresh_items()
        self.state_changed.emit()

    def state(self) -> DockState:
        return self._state

    def resize_hotspot_rects(self) -> list[QRect]:
        rects: list[QRect] = []
        handles = [self.edge_handle, self.corner_handle, *self._floating_resize_handles.values()]
        for handle in handles:
            if handle.isVisible() and handle.width() > 0 and handle.height() > 0:
                rects.append(QRect(handle.mapToGlobal(QPoint(0, 0)), handle.size()))
        return rects

    def is_resize_hotspot_at(self, global_pos: QPoint) -> bool:
        return any(rect.contains(global_pos) for rect in self.resize_hotspot_rects())

    def set_items(self, items: list[tuple[str, str, str]]) -> None:
        self._clear_items_layout()
        self._items.clear()
        for widget_id, icon_text, label in items:
            button = DockItemButton(widget_id, icon_text, label, self.items_container)
            button.activated.connect(self.widget_activated)
            button.dragged_out.connect(self.widget_drag_restored)
            button.close_requested.connect(self.widget_close_requested)
            if self._close_label:
                button.set_close_label(self._close_label)
            self.items_layout.addWidget(button)
            self._items[widget_id] = button
        self.items_layout.addStretch(1)
        self._refresh_items()

    def desired_rect(self, container_rect: QRect) -> QRect:
        state = self._state
        if state.position == DockPosition.FLOATING:
            return QRect(
                container_rect.x() + state.floating_x,
                container_rect.y() + state.floating_y,
                max(DOCK_FLOAT_MIN_WIDTH, state.floating_width),
                max(DOCK_FLOAT_MIN_HEIGHT, state.floating_height),
            )
        if state.position in (DockPosition.LEFT, DockPosition.RIGHT):
            thickness = (
                self._clamp_expanded_size(state.position, state.expanded_vertical_size)
                if state.expanded
                else self._clamp_collapsed_size(state.position, state.collapsed_thickness)
            )
            if state.position == DockPosition.LEFT:
                return QRect(container_rect.x(), container_rect.y(), thickness, container_rect.height())
            return QRect(container_rect.right() - thickness + 1, container_rect.y(), thickness, container_rect.height())
        thickness = (
            self._clamp_expanded_size(state.position, state.expanded_horizontal_size)
            if state.expanded
            else self._clamp_collapsed_size(state.position, state.collapsed_thickness)
        )
        if state.position == DockPosition.TOP:
            return QRect(container_rect.x(), container_rect.y(), container_rect.width(), thickness)
        return QRect(container_rect.x(), container_rect.bottom() - thickness + 1, container_rect.width(), thickness)

    def dock_capture_rect(self) -> QRect:
        return QRect(self.mapToGlobal(self.rect().topLeft()), self.size())

    def toggle_expanded(self) -> None:
        self._state.expanded = not self._state.expanded
        self._refresh_layout_direction()
        self.state_changed.emit()

    def dock_to(self, position: str) -> None:
        self._state.position = position
        if position != DockPosition.FLOATING:
            self._state.last_docked_position = position
        self._normalize_state()
        self.state_changed.emit()

    def toggle_floating(self) -> None:
        self._state.position = DockPosition.FLOATING if self._state.position != DockPosition.FLOATING else (self._state.last_docked_position or DockPosition.LEFT)
        self._normalize_state()
        self.state_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._drag_pending = True
        self._dragging = False
        self._drag_origin = event.globalPosition().toPoint()
        self._drag_offset = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (self._drag_pending or self._dragging):
            return super().mouseMoveEvent(event)
        global_pos = event.globalPosition().toPoint()
        if self._drag_pending and (global_pos - self._drag_origin).manhattanLength() >= 15:
            self._dragging = True
            self._drag_pending = False
        if not self._dragging:
            return super().mouseMoveEvent(event)
        container_rect = self._container_rect_provider() if self._container_rect_provider else QRect()
        if not container_rect.isNull():
            preview = self._preview_for_point(global_pos, container_rect)
            self.preview_changed.emit(preview)
        if self._state.position == DockPosition.FLOATING and not container_rect.isNull():
            local = global_pos - container_rect.topLeft() - self._drag_offset
            self._state.floating_x = max(0, local.x())
            self._state.floating_y = max(0, local.y())
            self.state_changed.emit()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        global_pos = event.globalPosition().toPoint()
        container_rect = self._container_rect_provider() if self._container_rect_provider else QRect()
        if self._dragging and not container_rect.isNull():
            preview = self._preview_for_point(global_pos, container_rect)
            if preview in {DockPosition.LEFT, DockPosition.RIGHT, DockPosition.TOP, DockPosition.BOTTOM}:
                self._state.position = preview
                self._state.last_docked_position = preview
            else:
                self._state.position = DockPosition.FLOATING
                local = global_pos - container_rect.topLeft() - self._drag_offset
                self._state.floating_x = max(0, local.x())
                self._state.floating_y = max(0, local.y())
            self._normalize_state()
            self.state_changed.emit()
        self._drag_pending = False
        self._dragging = False
        self.preview_changed.emit('')
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._state.position == DockPosition.FLOATING:
            self._state.position = self._state.last_docked_position or DockPosition.LEFT
            self._normalize_state()
            self.state_changed.emit()
        super().mouseDoubleClickEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.edge_handle:
            return self._handle_edge_resize(event)
        if watched is self.corner_handle or watched in self._floating_resize_handles.values():
            return self._handle_floating_resize(watched, event)
        return super().eventFilter(watched, event)

    def _handle_edge_resize(self, event) -> bool:
        if self._state.position == DockPosition.FLOATING:
            return False
        if event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            self._set_handle_hovered(self.edge_handle, True)
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self._set_handle_hovered(self.edge_handle, False)
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            return self._edge_resize_press(event)
        if event.type() == QEvent.Type.MouseMove and self._resize_edge:
            return self._edge_resize_move(event)
        if event.type() == QEvent.Type.MouseButtonRelease and self._resize_edge:
            return self._edge_resize_release()
        return False

    @staticmethod
    def _edge_resize_delta(position: str, delta: QPoint) -> int:
        if position == DockPosition.LEFT:
            return delta.x()
        if position == DockPosition.RIGHT:
            return -delta.x()
        if position == DockPosition.TOP:
            return delta.y()
        return -delta.y()

    def _edge_resize_press(self, event) -> bool:
        self._resize_edge = True
        self._resize_origin = event.globalPosition().toPoint()
        self._resize_started_collapsed = not self._state.expanded
        position = self._state.position
        if self._resize_started_collapsed:
            self._size_origin = self._clamp_collapsed_size(position, self._state.collapsed_thickness)
        elif position in (DockPosition.LEFT, DockPosition.RIGHT):
            self._size_origin = self._clamp_expanded_size(position, self._state.expanded_vertical_size)
        else:
            self._size_origin = self._clamp_expanded_size(position, self._state.expanded_horizontal_size)
        return True

    def _edge_resize_move(self, event) -> bool:
        delta = event.globalPosition().toPoint() - self._resize_origin
        position = self._state.position
        target_size = self._size_origin + self._edge_resize_delta(position, delta)

        if self._resize_started_collapsed:
            next_size = self._clamp_collapsed_size(position, target_size)
            if next_size != self._state.collapsed_thickness:
                self._state.collapsed_thickness = next_size
                self.state_changed.emit()
            return True

        next_size = self._clamp_expanded_size(position, target_size)
        if position in (DockPosition.LEFT, DockPosition.RIGHT):
            if next_size != self._state.expanded_vertical_size:
                self._state.expanded_vertical_size = next_size
                self.state_changed.emit()
        else:
            if next_size != self._state.expanded_horizontal_size:
                self._state.expanded_horizontal_size = next_size
                self.state_changed.emit()
        return True

    def _edge_resize_release(self) -> bool:
        self._resize_edge = False
        self._resize_started_collapsed = False
        self._set_handle_hovered(self.edge_handle, False)
        return True

    def _handle_floating_resize(self, watched: QFrame, event) -> bool:
        if self._state.position != DockPosition.FLOATING:
            return False
        if event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            self._set_handle_hovered(watched, True)
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self._set_handle_hovered(watched, False)
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            return self._float_resize_press(watched, event)
        if event.type() == QEvent.Type.MouseMove and self._resize_floating and self._resize_floating_direction:
            return self._float_resize_move(event)
        if event.type() == QEvent.Type.MouseButtonRelease and self._resize_floating:
            return self._float_resize_release(watched)
        return False

    def _float_resize_press(self, watched: QFrame, event) -> bool:
        self._resize_floating = True
        self._resize_floating_direction = str(watched.property('resizeDirection') or '')
        self._resize_origin = event.globalPosition().toPoint()
        self._float_rect_origin = QRect(
            self._state.floating_x,
            self._state.floating_y,
            self._state.floating_width,
            self._state.floating_height,
        )
        return True

    def _float_resize_move(self, event) -> bool:
        container_rect = self._container_rect_provider() if self._container_rect_provider else QRect()
        if container_rect.isNull():
            return True
        bounds = QRect(0, 0, container_rect.width(), container_rect.height())
        delta = event.globalPosition().toPoint() - self._resize_origin
        target = self._resize_local_rect(
            self._float_rect_origin,
            self._resize_floating_direction,
            delta,
            bounds,
            DOCK_FLOAT_MIN_WIDTH,
            DOCK_FLOAT_MIN_HEIGHT,
        )
        self._apply_float_rect(target)
        return True

    def _float_resize_release(self, watched: QFrame) -> bool:
        self._resize_floating = False
        self._set_handle_hovered(watched, False)
        self._resize_floating_direction = ''
        return True

    def _apply_float_rect(self, target: QRect) -> None:
        if (target.x() != self._state.floating_x or target.y() != self._state.floating_y
                or target.width() != self._state.floating_width or target.height() != self._state.floating_height):
            self._state.floating_x = target.x()
            self._state.floating_y = target.y()
            self._state.floating_width = target.width()
            self._state.floating_height = target.height()
            self.state_changed.emit()

    def _resize_local_rect(
        self,
        origin: QRect,
        direction: str,
        delta: QPoint,
        bounds: QRect,
        min_width: int,
        min_height: int,
    ) -> QRect:
        return compute_resized_rect(origin, direction, delta, bounds, min_width, min_height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_layout_direction()
        if self._state.position in (DockPosition.LEFT, DockPosition.RIGHT):
            self.edge_handle.setGeometry(self.width() - DOCK_EDGE_HOTZONE if self._state.position == DockPosition.LEFT else 0, 0, DOCK_EDGE_HOTZONE, self.height())
            self.edge_handle.setCursor(Qt.CursorShape.SizeHorCursor)
            self.edge_handle.show()
        elif self._state.position in (DockPosition.TOP, DockPosition.BOTTOM):
            self.edge_handle.setGeometry(0, self.height() - DOCK_EDGE_HOTZONE if self._state.position == DockPosition.TOP else 0, self.width(), DOCK_EDGE_HOTZONE)
            self.edge_handle.setCursor(Qt.CursorShape.SizeVerCursor)
            self.edge_handle.show()
        else:
            self.edge_handle.hide()
            self.edge_handle.setGeometry(0, 0, 0, 0)

        if self._state.position == DockPosition.FLOATING:
            edge = DOCK_FLOAT_EDGE_HOTZONE
            corner = DOCK_FLOAT_CORNER_HOTZONE
            inner_height = max(0, self.height() - corner * 2)
            inner_width = max(0, self.width() - corner * 2)
            self._floating_resize_handles['left'].setGeometry(0, corner, edge, inner_height)
            self._floating_resize_handles['right'].setGeometry(self.width() - edge, corner, edge, inner_height)
            self._floating_resize_handles['top'].setGeometry(corner, 0, inner_width, edge)
            self._floating_resize_handles['bottom'].setGeometry(corner, self.height() - edge, inner_width, edge)
            self._floating_resize_handles['top_left'].setGeometry(0, 0, corner, corner)
            self._floating_resize_handles['top_right'].setGeometry(self.width() - corner, 0, corner, corner)
            self._floating_resize_handles['bottom_left'].setGeometry(0, self.height() - corner, corner, corner)
            for handle in self._floating_resize_handles.values():
                handle.show()
                handle.raise_()
            self.corner_handle.setGeometry(
                self.width() - DOCK_FLOAT_RESIZE_HINT,
                self.height() - DOCK_FLOAT_RESIZE_HINT,
                DOCK_FLOAT_RESIZE_HINT,
                DOCK_FLOAT_RESIZE_HINT,
            )
            self.corner_handle.show()
            self.corner_handle.raise_()
        else:
            self.corner_handle.hide()
            self.corner_handle.setGeometry(0, 0, 0, 0)
            for handle in self._floating_resize_handles.values():
                handle.hide()
                handle.setGeometry(0, 0, 0, 0)

    def _clear_items_layout(self) -> None:
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _preview_for_point(self, global_pos: QPoint, container_rect: QRect) -> str:
        edge = 40
        x = global_pos.x() - container_rect.x()
        y = global_pos.y() - container_rect.y()
        if x < edge:
            return DockPosition.LEFT
        if x > container_rect.width() - edge:
            return DockPosition.RIGHT
        if y < edge:
            return DockPosition.TOP
        if y > container_rect.height() - edge:
            return DockPosition.BOTTOM
        return DockPosition.FLOATING

    def _refresh_layout_direction(self) -> None:
        position = self._state.position
        if position in (DockPosition.LEFT, DockPosition.RIGHT, DockPosition.FLOATING):
            self.root_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.items_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.root_layout.setAlignment(self.toggle_button, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        else:
            self.root_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.items_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.root_layout.setAlignment(self.toggle_button, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.items_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._refresh_items()

    def _refresh_items(self) -> None:
        expanded = self._state.expanded
        floating = self._state.position == DockPosition.FLOATING
        for button in self._items.values():
            button.refresh_text(expanded, floating)
        if self._state.position == DockPosition.LEFT:
            self.toggle_button.setText('›' if expanded else '‹')
        elif self._state.position == DockPosition.RIGHT:
            self.toggle_button.setText('‹' if expanded else '›')
        elif self._state.position == DockPosition.TOP:
            self.toggle_button.setText('⌄' if expanded else '›')
        elif self._state.position == DockPosition.BOTTOM:
            self.toggle_button.setText('⌃' if expanded else '›')
        else:
            self.toggle_button.hide()
            return
        self.toggle_button.show()

    def _set_handle_hovered(self, handle: QFrame, hovered: bool) -> None:
        handle.setProperty('hovered', hovered)
        self.style().unpolish(handle)
        self.style().polish(handle)

    def _normalize_state(self) -> None:
        position = self._state.position if self._state.position != DockPosition.FLOATING else (self._state.last_docked_position or DockPosition.LEFT)
        self._state.collapsed_thickness = self._clamp_collapsed_size(position, self._state.collapsed_thickness or DOCK_COLLAPSED_THICKNESS)
        self._state.expanded_vertical_size = self._clamp_expanded_size(DockPosition.LEFT, self._state.expanded_vertical_size or DOCK_EXPANDED_SIDE)
        self._state.expanded_horizontal_size = self._clamp_expanded_size(DockPosition.TOP, self._state.expanded_horizontal_size or DOCK_EXPANDED_TOP)
        if not self._state.floating_width:
            self._state.floating_width = DOCK_FLOAT_WIDTH
        if not self._state.floating_height:
            self._state.floating_height = DOCK_FLOAT_HEIGHT

    def _clamp_collapsed_size(self, position: str, size: int) -> int:
        maximum = DOCK_COLLAPSED_MAX_SIDE if position in (DockPosition.LEFT, DockPosition.RIGHT) else DOCK_COLLAPSED_MAX_TOP
        return max(DOCK_COLLAPSED_MIN, min(maximum, int(size)))

    def _clamp_expanded_size(self, position: str, size: int) -> int:
        if position in (DockPosition.LEFT, DockPosition.RIGHT):
            return max(DOCK_EXPANDED_SIDE_MIN, min(DOCK_EXPANDED_SIDE_MAX, int(size)))
        return max(DOCK_EXPANDED_TOP_MIN, min(DOCK_EXPANDED_TOP_MAX, int(size)))
