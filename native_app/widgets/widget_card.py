from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QPushButton, QVBoxLayout, QWidget

from ..theme import _fs, current_palette
from ..ui_tokens import WIDGET_RESIZE_CORNER, WIDGET_RESIZE_EDGE, WIDGET_RESIZE_HINT

from PyQt6.QtWidgets import QLabel
from .common import compute_resized_rect


class WidgetCard(QFrame):
    geometry_edited = pyqtSignal(str)
    geometry_live = pyqtSignal()  # emitted on every move/resize (during drag, not just release)
    interaction_finished = pyqtSignal(str)
    close_requested = pyqtSignal(str)  # widget_id — request to hide/dock this card
    floated = pyqtSignal(str)  # widget_id — card became a floating window
    unfloated = pyqtSignal(str)  # widget_id — card returned to workspace

    def __init__(self, widget_id: str, *, min_size: QSize, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.setObjectName("WidgetCard")
        self.setMouseTracking(True)
        self._min_size = min_size
        self.setMinimumSize(min_size)
        self._drag_origin = QPoint()
        self._resize_origin = QPoint()
        self._frame_origin = QRect()
        self._dragging = False
        self._resizing = False
        self._resize_direction = ""
        self._drag_strip_height = 36
        self._pinned = False
        self._floating = False
        self._workspace_parent = None

        self._content_host = QWidget(self)
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(10, self._drag_strip_height, 10, 10)
        self._content_layout.setSpacing(8)

        self._drag_strip = QWidget(self)
        self._drag_strip.setObjectName("WidgetDragStrip")
        self._drag_strip.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_strip.setMouseTracking(True)
        self._drag_strip.setAcceptDrops(True)  # block drops from reaching content below

        self._grip = QPushButton("⠇", self._drag_strip)
        self._grip.setObjectName("WidgetGrip")
        self._grip.setCursor(Qt.CursorShape.OpenHandCursor)
        self._grip.setFixedSize(48, 28)

        self._title_label = QLabel("", self._drag_strip)
        self._title_label.setObjectName("WidgetCardTitle")
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        p = current_palette()
        self._title_label.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; background: transparent; "
            f"border: none; letter-spacing: 1px;"
        )

        self._close_btn = QPushButton("×", self._drag_strip)
        self._close_btn.setObjectName("WidgetCloseBtn")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setFlat(True)
        self._close_btn.setToolTip("")  # set by retranslate_ui
        self._close_btn.clicked.connect(self._close_action)

        self._pin_btn = QPushButton("📌", self._drag_strip)
        self._pin_btn.setObjectName("WidgetPinBtn")
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setFixedSize(24, 24)
        self._pin_btn.setFlat(True)
        self._pin_btn.setToolTip("Pin")
        self._pin_btn.clicked.connect(lambda: self._toggle_pin())

        self._resize_handle = QPushButton("◢", self)
        self._resize_handle.setObjectName("WidgetResizeHandle")
        self._resize_handle.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self._resize_handle.setFixedSize(WIDGET_RESIZE_HINT, WIDGET_RESIZE_HINT)
        self._resize_handle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._resize_handles: dict[str, QFrame] = {}
        for direction, cursor in {
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
        }.items():
            handle = QFrame(self)
            handle.setObjectName("WidgetResizeCornerHandle" if "_" in direction else "WidgetResizeEdgeHandle")
            handle.setCursor(cursor)
            handle.setProperty("resizeDirection", direction)
            handle.installEventFilter(self)
            self._resize_handles[direction] = handle

        self._drag_strip.installEventFilter(self)
        self._grip.installEventFilter(self)
        self._update_pin_style()
        self.retranslate_ui("Drag to move", "Drag to resize")

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def apply_theme(self) -> None:
        p = current_palette()
        self._title_label.setStyleSheet(
            f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; background: transparent; "
            f"border: none; letter-spacing: 1px;"
        )
        self._update_pin_style()

    def set_content(self, widget: QWidget) -> None:
        if self._content_layout.count():
            old_widget = self._content_layout.takeAt(0).widget()
            if old_widget is not None:
                old_widget.setParent(None)
        self._content_layout.addWidget(widget)

    def retranslate_ui(self, grip_title: str, resize_title: str, close_title: str = "") -> None:
        self._drag_strip.setToolTip(grip_title)
        self._grip.setToolTip(grip_title)
        self._resize_handle.setToolTip(resize_title)
        if close_title:
            self._close_btn.setToolTip(close_title)

    def resize_hotspot_rects(self) -> list[QRect]:
        rects: list[QRect] = []
        for handle in self._resize_handles.values():
            if handle.isVisible() and handle.width() > 0 and handle.height() > 0:
                rects.append(QRect(handle.mapToGlobal(QPoint(0, 0)), handle.size()))
        return rects

    def is_resize_hotspot_at(self, global_pos: QPoint) -> bool:
        return any(rect.contains(global_pos) for rect in self.resize_hotspot_rects())

    def mousePressEvent(self, event) -> None:
        self.raise_()
        super().mousePressEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._drag_strip or watched is self._grip:
            return self._handle_drag_event(watched, event)
        if watched in self._resize_handles.values():
            return self._handle_resize_event(watched, event)
        return super().eventFilter(watched, event)

    def _handle_drag_event(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            if self._floating:
                back_action = menu.addAction("↩ 收回工作区")
            else:
                back_action = None
            close_action = menu.addAction("✕ 收纳")
            chosen = menu.exec(event.globalPosition().toPoint())
            if chosen is close_action:
                if self._floating and self._workspace_parent:
                    self.float_back(self._workspace_parent)
                self.close_requested.emit(self.widget_id)
            elif back_action and chosen is back_action:
                if self._workspace_parent:
                    self.float_back(self._workspace_parent)
            return True
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            local_pos = event.position().toPoint()
            if watched is self._drag_strip:
                child = self._drag_strip.childAt(local_pos)
                if child is self._pin_btn or child is self._close_btn:
                    return False
            self.raise_()
            self._dragging = True
            self._drag_origin = event.globalPosition().toPoint()
            self._frame_origin = self.geometry()
            self._drag_strip.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._grip.setCursor(Qt.CursorShape.ClosedHandCursor)
            return True
        if event.type() == QEvent.Type.MouseMove and self._dragging:
            gpos = event.globalPosition().toPoint()
            delta = gpos - self._drag_origin
            if not self._floating and self.parentWidget() is not None:
                parent_rect = QRect(self.parentWidget().mapToGlobal(QPoint(0, 0)),
                                    self.parentWidget().size())
                # If cursor is outside workspace bounds, float out
                if not parent_rect.contains(gpos):
                    self.float_out(gpos)
                    self._drag_origin = gpos
                    self._frame_origin = self.geometry()
                    return True
            target = QRect(self._frame_origin)
            target.moveTopLeft(self._frame_origin.topLeft() + delta)
            self._apply_geometry(target)
            self.geometry_edited.emit(self.widget_id)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and self._dragging:
            self._dragging = False
            self._drag_strip.setCursor(Qt.CursorShape.OpenHandCursor)
            self._grip.setCursor(Qt.CursorShape.OpenHandCursor)
            self.interaction_finished.emit(self.widget_id)
            return True
        return False

    def _handle_resize_event(self, watched: QFrame, event) -> bool:
        direction = str(watched.property("resizeDirection") or "")
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = True
            self._resize_direction = direction
            self._resize_origin = event.globalPosition().toPoint()
            self._frame_origin = self.geometry()
            return True
        if event.type() == QEvent.Type.MouseMove and self._resizing and self._resize_direction:
            delta = event.globalPosition().toPoint() - self._resize_origin
            target = self._resized_rect(self._frame_origin, self._resize_direction, delta)
            self.setGeometry(target)
            self.geometry_edited.emit(self.widget_id)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and self._resizing:
            self._resizing = False
            self._resize_direction = ""
            self.interaction_finished.emit(self.widget_id)
            return True
        return False

    def _resized_rect(self, origin: QRect, direction: str, delta: QPoint) -> QRect:
        if self.parentWidget() is not None and not self._floating:
            bounds = self.parentWidget().rect()
        else:
            # Floating: use screen geometry as bounds
            from PyQt6.QtGui import QGuiApplication
            screen = QGuiApplication.screenAt(origin.center())
            bounds = screen.availableGeometry() if screen else QRect(0, 0, 3840, 2160)
        return compute_resized_rect(origin, direction, delta, bounds, self._min_size.width(), self._min_size.height())

    def _close_action(self) -> None:
        if self._floating and self._workspace_parent:
            self.float_back(self._workspace_parent)
        self.close_requested.emit(self.widget_id)

    def _update_pin_style(self) -> None:
        p = current_palette()
        color = p['accent_text'] if self._pinned else p['text_dim']
        self._pin_btn.setStyleSheet(
            f"color: {color}; background: transparent; border: none; font-size: {_fs('fs_12')};"
        )
        self._close_btn.setStyleSheet(
            f"color: {p['text_dim']}; background: transparent; border: none; font-size: {_fs('fs_12')};"
        )

    def _toggle_pin(self) -> None:
        self._pinned = not self._pinned
        self._update_pin_style()
        if self._floating:
            geo = self.geometry()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._pinned)
            self.setGeometry(geo)
            self.show()
        elif self._pinned:
            self.raise_()

    @property
    def is_pinned(self) -> bool:
        return self._pinned

    @property
    def is_floating(self) -> bool:
        return self._floating

    def float_out(self, global_pos: QPoint) -> None:
        """Detach from workspace and become an independent floating window."""
        if self._floating:
            return
        self._floating = True
        self._pinned = True  # default always on top
        self._workspace_parent = self.parentWidget()
        size = self.size()
        self.setParent(None)
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.move(global_pos - QPoint(size.width() // 2, 16))
        self.resize(size)
        self.show()
        self._update_pin_style()
        self.floated.emit(self.widget_id)

    def float_back(self, parent: QWidget) -> None:
        """Re-attach to the workspace as a child widget."""
        if not self._floating:
            return
        self._floating = False
        self._pinned = False
        size = self.size()
        self.setParent(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.resize(size)
        self.show()
        # Re-raise drag strip and resize handles after reparent (z-order resets)
        self._drag_strip.raise_()
        for handle in self._resize_handles.values():
            handle.raise_()
        self._resize_handle.raise_()
        self._update_pin_style()
        self.unfloated.emit(self.widget_id)

    def _apply_geometry(self, rect: QRect) -> None:
        if self.parentWidget() is None or self._floating:
            from PyQt6.QtGui import QGuiApplication
            screen = QGuiApplication.screenAt(rect.center())
            if screen:
                avail = screen.availableGeometry()
                grab = self._drag_strip_height
                rect.moveLeft(max(avail.left() - rect.width() + grab,
                                  min(rect.x(), avail.right() - grab)))
                rect.moveTop(max(avail.top(),
                                  min(rect.y(), avail.bottom() - grab)))
            self.setGeometry(rect)
            return
        bounds = self.parentWidget().rect()
        width = min(max(self._min_size.width(), rect.width()), bounds.width())
        height = min(max(self._min_size.height(), rect.height()), bounds.height())
        x = max(bounds.left(), min(rect.x(), bounds.right() - width + 1))
        y = max(bounds.top(), min(rect.y(), bounds.bottom() - height + 1))
        self.setGeometry(x, y, width, height)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.geometry_live.emit()

    def resizeEvent(self, event) -> None:
        self._content_host.setGeometry(0, 0, self.width(), self.height())
        self._drag_strip.setGeometry(0, 0, self.width(), self._drag_strip_height)
        self._grip.move(0, max(0, (self._drag_strip.height() - self._grip.height()) // 2))
        title_x = self._grip.width() + 4
        btn_area = self._close_btn.width() + self._pin_btn.width() + 12
        title_w = self.width() - title_x - btn_area
        self._title_label.setGeometry(title_x, 0, max(0, title_w), self._drag_strip.height())
        cy = max(0, (self._drag_strip.height() - self._close_btn.height()) // 2)
        self._close_btn.move(self.width() - self._close_btn.width() - self._pin_btn.width() - 8, cy)
        self._pin_btn.move(self.width() - self._pin_btn.width() - 6, cy)

        edge = WIDGET_RESIZE_EDGE
        corner = WIDGET_RESIZE_CORNER
        inner_height = max(0, self.height() - corner * 2)
        inner_width = max(0, self.width() - corner * 2)
        self._resize_handles["left"].setGeometry(0, corner, edge, inner_height)
        self._resize_handles["right"].setGeometry(self.width() - edge, corner, edge, inner_height)
        self._resize_handles["top"].setGeometry(corner, 0, inner_width, edge)
        self._resize_handles["bottom"].setGeometry(corner, self.height() - edge, inner_width, edge)
        self._resize_handles["top_left"].setGeometry(0, 0, corner, corner)
        self._resize_handles["top_right"].setGeometry(self.width() - corner, 0, corner, corner)
        self._resize_handles["bottom_left"].setGeometry(0, self.height() - corner, corner, corner)
        self._resize_handles["bottom_right"].setGeometry(self.width() - corner, self.height() - corner, corner, corner)

        self._resize_handle.move(self.width() - self._resize_handle.width(), self.height() - self._resize_handle.height())
        self.geometry_live.emit()

        self._drag_strip.raise_()
        for handle in self._resize_handles.values():
            handle.raise_()
        self._resize_handle.raise_()
        super().resizeEvent(event)
