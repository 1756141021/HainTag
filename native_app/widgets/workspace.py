from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from ..models import WidgetState
from .widget_card import WidgetCard


@dataclass
class DockQueryResult:
    """Result of a dock proximity query: the target rectangle and dock position."""
    rect: QRect
    position: str


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class Workspace(QWidget):
    dock_requested = pyqtSignal(str)
    layout_changed = pyqtSignal()
    image_dropped = pyqtSignal(str)  # Emitted when an image is dropped onto empty space

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self._cards: dict[str, WidgetCard] = {}
        self._dock_query: Callable[[], DockQueryResult | None] | None = None
        self._bg_pixmap: QPixmap | None = None
        self._bg_opacity: float = 0.4
        self._bg_brightness: float = 0.5

    def set_background_image(self, path: str, blur: int = 30, opacity: int = 40, brightness: int = 50) -> None:
        """Set a background image with blur, opacity (0-100), and brightness (0-100)."""
        self._bg_opacity = max(0, min(100, opacity)) / 100.0
        self._bg_brightness = max(0, min(100, brightness)) / 100.0
        if not path or not Path(path).exists():
            self._bg_pixmap = None
            self.update()
            return
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self._bg_pixmap = None
                self.update()
                return
            # Apply background image effects through the same settings exposed in the UI.
            blur_radius = max(0, min(100, blur))
            brightness_factor = 0.15 + self._bg_brightness * 1.7
            if blur_radius > 0 or abs(brightness_factor - 1.0) > 0.01:
                try:
                    from PIL import Image, ImageEnhance, ImageFilter
                    # Scale down for fast blur
                    small_w = max(1, pixmap.width() // 4)
                    small_h = max(1, pixmap.height() // 4)
                    small_pix = pixmap.scaled(small_w, small_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    img = small_pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                    ptr = img.bits()
                    ptr.setsize(img.sizeInBytes())
                    pil_img = Image.frombytes('RGBA', (img.width(), img.height()), bytes(ptr))
                    if blur_radius > 0:
                        pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=blur_radius // 2 + 1))
                    if abs(brightness_factor - 1.0) > 0.01:
                        pil_img = ImageEnhance.Brightness(pil_img).enhance(brightness_factor)
                    data = pil_img.tobytes()
                    result = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888).copy()
                    pixmap = QPixmap.fromImage(result)
                except Exception:
                    pass  # Fall through to unblurred pixmap
            self._bg_pixmap = pixmap
        except Exception:
            self._bg_pixmap = None
        self.update()

    def clear_background_image(self) -> None:
        self._bg_pixmap = None
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._bg_pixmap is not None and self._bg_opacity > 0:
            painter = QPainter(self)
            painter.setOpacity(self._bg_opacity)
            scaled = self._bg_pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()

    def set_dock_query(self, callback: Callable[[], DockQueryResult | None]) -> None:
        self._dock_query = callback

    def add_card(self, card: WidgetCard) -> None:
        self._prune_deleted_cards()
        card.setParent(self)
        card.show()
        card.geometry_edited.connect(self._on_card_edited)
        card.interaction_finished.connect(self._on_card_finished)
        card.close_requested.connect(lambda wid: self.dock_requested.emit(wid))
        card.destroyed.connect(lambda *_args, widget_id=card.widget_id, ref=card: self._forget_card(widget_id, ref))
        self._cards[card.widget_id] = card

    def remove_card(self, widget_id: str) -> None:
        card = self.card(widget_id)
        if card is None:
            return
        self._forget_card(widget_id, card)
        if not sip.isdeleted(card):
            card.setParent(None)
            card.deleteLater()
        self.layout_changed.emit()

    def card(self, widget_id: str) -> WidgetCard | None:
        self._prune_deleted_cards()
        return self._cards.get(widget_id)

    def all_cards(self) -> list[WidgetCard]:
        self._prune_deleted_cards()
        return list(self._cards.values())

    def visible_cards(self, *, exclude: WidgetCard | None = None) -> list[WidgetCard]:
        self._prune_deleted_cards()
        return [card for card in self._cards.values() if card is not exclude and card.isVisible()]

    def is_card_resize_hotspot_at(self, global_pos: QPoint) -> bool:
        return any(card.is_resize_hotspot_at(global_pos) for card in self.visible_cards())

    def find_free_position(self, size: QSize, *, exclude: WidgetCard | None = None) -> QRect:
        width = min(size.width(), max(180, self.width() - 10))
        height = min(size.height(), max(120, self.height() - 10))
        others = [card.geometry() for card in self.visible_cards(exclude=exclude)]
        center_rect = QRect((self.width() - width) // 2, (self.height() - height) // 2, width, height)
        if not any(rect.intersects(center_rect) for rect in others):
            return center_rect
        step = 20
        for y in range(10, max(11, self.height() - height + 1), step):
            for x in range(10, max(11, self.width() - width + 1), step):
                candidate = QRect(x, y, width, height)
                if not any(rect.intersects(candidate) for rect in others):
                    return candidate
        return center_rect

    def clamp_card(self, card: WidgetCard) -> None:
        if sip.isdeleted(card):
            return
        geometry = card.geometry()
        grab = 40  # at least this many pixels must remain visible
        min_x = grab - geometry.width()
        min_y = grab - geometry.height()
        max_x = self.width() - grab
        max_y = self.height() - grab
        geometry.moveLeft(max(min_x, min(geometry.x(), max_x)))
        geometry.moveTop(max(min_y, min(geometry.y(), max_y)))
        card.setGeometry(geometry)

    def resolve_overlap(self, card: WidgetCard) -> None:
        # Cards can freely overlap like PPT layers — no auto-repositioning
        pass

    def restore_card(self, card: WidgetCard, state: WidgetState | None = None, drop_point: QPoint | None = None) -> None:
        if sip.isdeleted(card):
            return
        card.show()
        if drop_point is not None:
            local = self.mapFromGlobal(drop_point)
            rect = QRect(local.x() - card.width() // 2, local.y() - 24, card.width(), card.height())
            card.setGeometry(rect)
            self.clamp_card(card)
        elif state is not None:
            card.setGeometry(state.x, state.y, state.width, state.height)
            self.clamp_card(card)
        else:
            current = card.geometry()
            if current.width() > 0 and current.height() > 0:
                self.clamp_card(card)
            else:
                card.setGeometry(self.find_free_position(card.size(), exclude=card))
        self.resolve_overlap(card)
        self.layout_changed.emit()

    def hide_card(self, widget_id: str) -> None:
        card = self.card(widget_id)
        if card is not None:
            card.hide()
            self.layout_changed.emit()

    def widget_states(self) -> list[WidgetState]:
        states: list[WidgetState] = []
        for card in self.all_cards():
            geometry = card.geometry()
            states.append(
                WidgetState(
                    widget_id=card.widget_id,
                    visible=card.isVisible(),
                    docked=not card.isVisible(),
                    x=geometry.x(),
                    y=geometry.y(),
                    width=geometry.width(),
                    height=geometry.height(),
                    dock_slot="main" if not card.isVisible() else "",
                )
            )
        return states

    def apply_widget_states(self, states: list[WidgetState]) -> None:
        for state in states:
            card = self.card(state.widget_id)
            if card is None:
                continue
            card.setGeometry(state.x, state.y, state.width, state.height)
            if state.visible and not state.docked:
                card.show()
            else:
                card.hide()
            self.clamp_card(card)

    def scale_layout(self, scale_x: float, scale_y: float) -> None:
        for card in self.all_cards():
            if not card.isVisible():
                continue
            rect = card.geometry()
            scaled = QRect(
                int(round(rect.x() * scale_x)),
                int(round(rect.y() * scale_y)),
                max(card.minimumWidth(), int(round(rect.width() * scale_x))),
                max(card.minimumHeight(), int(round(rect.height() * scale_y))),
            )
            card.setGeometry(scaled)
            self.clamp_card(card)
            self.resolve_overlap(card)
        self.layout_changed.emit()

    def resizeEvent(self, event) -> None:
        for card in self.visible_cards():
            self.clamp_card(card)
        super().resizeEvent(event)

    def _on_card_edited(self, _widget_id: str) -> None:
        self.layout_changed.emit()

    def _on_card_finished(self, widget_id: str) -> None:
        card = self.card(widget_id)
        if card is None:
            return
        dock_info = self._dock_query() if self._dock_query is not None else None
        if dock_info is not None:
            dock_rect = dock_info.rect
            card_rect = QRect(card.mapToGlobal(card.rect().topLeft()), card.size())
            sense = 30
            should_dock = False
            if dock_info.position == "floating":
                expanded = dock_rect.adjusted(-sense, -sense, sense, sense)
                should_dock = expanded.intersects(card_rect)
            elif dock_info.position == "left":
                should_dock = card_rect.left() < dock_rect.right() + sense
            elif dock_info.position == "right":
                should_dock = card_rect.right() > dock_rect.left() - sense
            elif dock_info.position == "top":
                should_dock = card_rect.top() < dock_rect.bottom() + sense
            elif dock_info.position == "bottom":
                should_dock = card_rect.bottom() > dock_rect.top() - sense
            if should_dock:
                self.dock_requested.emit(widget_id)
                return
        self.resolve_overlap(card)
        self.layout_changed.emit()

    def _forget_card(self, widget_id: str, card: WidgetCard | None = None) -> None:
        current = self._cards.get(widget_id)
        if current is None:
            return
        if card is not None and current is not card:
            return
        self._cards.pop(widget_id, None)

    def _prune_deleted_cards(self) -> None:
        stale_widget_ids = [widget_id for widget_id, card in self._cards.items() if card is None or sip.isdeleted(card)]
        for widget_id in stale_widget_ids:
            self._cards.pop(widget_id, None)

    # ── Drag-and-drop: images dropped on workspace empty space ──

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in _IMAGE_EXTS:
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if Path(path).suffix.lower() in _IMAGE_EXTS:
                    self.image_dropped.emit(path)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)
