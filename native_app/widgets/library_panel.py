"""Library Panel — two-step scroll drawer for Artist Library and OC Library.

Design language: Hypergryph / Arknights — industrial frosted glass,
restrained accent, geometric minimalism, line-driven, breathing room.
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..models import ArtistEntry, OCEntry
from ..storage import AppStorage
from ..theme import _fs, current_palette
from .common import ToggleSwitch

_IMAGE_EXTS = "Images (*.png *.jpg *.jpeg *.webp *.bmp)"

SECTION_ARTIST = "artist"
SECTION_OC = "oc"


def _p() -> dict[str, str]:
    return current_palette()


# ── Shared style helpers (DRY) ──

def _input_style(p: dict, fs: str = 'fs_10', padding: str = '3px 6px') -> str:
    return (f"background: {p['bg']}; color: {p['text']}; border: 1px solid {p['line']}; "
            f"border-radius: 3px; padding: {padding}; font-size: {_fs(fs)};")


def _del_btn_style(p: dict, fs: str = 'fs_11') -> str:
    return f"color: {p['text_dim']}; background: transparent; border: none; font-size: {_fs(fs)};"


def _arrow_style(p: dict) -> str:
    return f"color: {p['accent_text']}; font-size: {_fs('fs_9')}; background: transparent; border: none;"


def _header_style(p: dict, expanded: bool) -> str:
    if expanded:
        return (f"background: {p['bg_surface']}; border: 1px solid {p['line']}; "
                f"border-bottom: none; border-radius: 4px 4px 0 0;")
    return f"background: {p['bg_surface']}; border: 1px solid {p['line']}; border-radius: 4px;"


def _dim_label_style(p: dict) -> str:
    return f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; border: none; letter-spacing: 1px;"


# ═══════════════════════════════════════════════════════════
#  Reference Image Grid
# ═══════════════════════════════════════════════════════════

class _RefImageGrid(QWidget):
    """Reference image display. Two modes:

    - vertical=True (artist): full-width images stacked vertically, click to remove
    - vertical=False (OC): small horizontal thumbnails
    """

    changed = pyqtSignal()

    def __init__(self, storage: AppStorage, thumb_size: int = 40,
                 vertical: bool = False, parent=None):
        super().__init__(parent)
        self._storage = storage
        self._paths: list[str] = []
        self._thumb_size = thumb_size
        self._vertical = vertical

        if vertical:
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 2, 0, 2)
            self._layout.setSpacing(6)
        else:
            self._layout = QHBoxLayout(self)
            self._layout.setContentsMargins(0, 2, 0, 2)
            self._layout.setSpacing(4)

        self._add_btn = QPushButton("+", self)
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if vertical:
            self._add_btn.setFixedHeight(28)
        else:
            self._add_btn.setFixedSize(thumb_size, thumb_size)
        self._layout.addWidget(self._add_btn)
        self._add_btn.clicked.connect(self._pick_image)
        if not vertical:
            self._layout.addStretch()
        self._apply_btn_style()

    def _apply_btn_style(self):
        p = _p()
        self._add_btn.setStyleSheet(
            f"background: {p['bg_content']}; border: 1px dashed {p['line']}; "
            f"border-radius: 4px; color: {p['text_dim']}; font-size: {_fs('fs_14')};"
        )

    def set_paths(self, paths: list[str]):
        self._paths = list(paths)
        self._rebuild()

    def paths(self) -> list[str]:
        return list(self._paths)

    def _rebuild(self):
        # Remove all widgets except the add button (last for vertical, has stretch for horizontal)
        while self._layout.count() > (1 if self._vertical else 2):
            item = self._layout.takeAt(0)
            w = item.widget()
            if w and w is not self._add_btn:
                w.deleteLater()
        p = _p()
        insert_pos = 0
        for i, path in enumerate(self._paths):
            if self._vertical:
                # Full-width image
                thumb = QLabel(self)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb.setStyleSheet(
                    f"background: {p['bg_content']}; border: 1px solid {p['line']}; border-radius: 4px;"
                )
                thumb.setCursor(Qt.CursorShape.PointingHandCursor)
                if os.path.isfile(path):
                    pm = QPixmap(path).scaledToWidth(
                        max(180, self.width() - 8),
                        Qt.TransformationMode.SmoothTransformation)
                    thumb.setPixmap(pm)
                    thumb.setFixedHeight(pm.height() + 4)
                thumb.setToolTip("Click to remove")
                thumb.mousePressEvent = lambda _, idx=i: self._remove_image(idx)
                self._layout.insertWidget(insert_pos, thumb)
            else:
                # Small thumbnail
                ts = self._thumb_size
                thumb = QLabel(self)
                thumb.setFixedSize(ts, ts)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb.setStyleSheet(
                    f"background: {p['bg_content']}; border: 1px solid {p['line']}; border-radius: 4px;"
                )
                thumb.setCursor(Qt.CursorShape.PointingHandCursor)
                if os.path.isfile(path):
                    pm = QPixmap(path).scaled(QSize(ts - 4, ts - 4),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                    thumb.setPixmap(pm)
                thumb.setToolTip("Click to remove")
                thumb.mousePressEvent = lambda _, idx=i: self._remove_image(idx)
                self._layout.insertWidget(insert_pos, thumb)
            insert_pos += 1

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", _IMAGE_EXTS)
        if path:
            saved = self._storage.copy_library_image(path)
            self._paths.append(saved)
            self._rebuild()
            self.changed.emit()

    def _remove_image(self, idx: int):
        if 0 <= idx < len(self._paths):
            self._storage.remove_library_image(self._paths[idx])
            self._paths.pop(idx)
            self._rebuild()
            self.changed.emit()


# ═══════════════════════════════════════════════════════════
#  Artist Banner
# ═══════════════════════════════════════════════════════════

class ArtistBanner(QWidget):
    """Expandable entry card for an artist."""

    changed = pyqtSignal()
    delete_requested = pyqtSignal(object)

    def __init__(self, translator: Translator, storage: AppStorage,
                 entry: ArtistEntry | None = None, parent=None):
        super().__init__(parent)
        self._t = translator
        self._expanded = False
        p = _p()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header (always visible) ──
        self._header = QWidget(self)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            f"background: {p['bg_surface']}; border: 1px solid {p['line']}; border-radius: 4px;"
        )
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(10, 6, 6, 6)
        hl.setSpacing(8)

        self._arrow = QLabel("▸", self._header)
        self._arrow.setStyleSheet(_arrow_style(p))
        self._arrow.setFixedWidth(10)
        hl.addWidget(self._arrow)

        self._name_label = QLabel(translator.t("artist_name"), self._header)
        self._name_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_11')}; background: transparent; border: none;")
        hl.addWidget(self._name_label, 1)

        del_btn = QPushButton("×", self._header)
        del_btn.setFixedSize(16, 16)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(_del_btn_style(p))
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        hl.addWidget(del_btn)

        self._header.mousePressEvent = lambda e: self._toggle()
        root.addWidget(self._header)

        # ── Body (expandable) — image-dominant layout ──
        self._body = QWidget(self)
        self._body.setStyleSheet(
            f"background: {p['bg_content']}; border: 1px solid {p['line']}; "
            f"border-top: none; border-radius: 0 0 4px 4px;"
        )
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(8, 6, 8, 8)
        bl.setSpacing(4)

        # Reference images — hero area, full width
        self._ref_grid = _RefImageGrid(storage, vertical=True, parent=self._body)
        self._ref_grid.changed.connect(self.changed.emit)
        bl.addWidget(self._ref_grid)

        # Name — compact
        self._name_edit = QLineEdit(self._body)
        self._name_edit.setPlaceholderText(translator.t("artist_name"))
        self._name_edit.setStyleSheet(_input_style(p))
        self._name_edit.textChanged.connect(self._on_name_changed)
        bl.addWidget(self._name_edit)

        # LoRA / trigger — compact with copy button
        string_row = QHBoxLayout()
        string_row.setSpacing(4)
        self._string_edit = QLineEdit(self._body)
        self._string_edit.setPlaceholderText(translator.t("artist_string"))
        self._string_edit.setStyleSheet(_input_style(p))
        self._string_edit.textChanged.connect(lambda: self.changed.emit())
        string_row.addWidget(self._string_edit, 1)
        copy_btn = QPushButton("Copy", self._body)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setFixedHeight(22)
        copy_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; border: none; "
            f"border-radius: 3px; padding: 0 10px; font-size: {_fs('fs_9')}; letter-spacing: 1px;"
        )
        copy_btn.clicked.connect(self._copy_string)
        string_row.addWidget(copy_btn)
        bl.addLayout(string_row)

        self._body.hide()
        root.addWidget(self._body)

        if entry:
            self.set_entry(entry)

    def apply_theme(self):
        p = _p()
        self._header.setStyleSheet(_header_style(p, self._expanded))
        self._arrow.setStyleSheet(_arrow_style(p))
        self._name_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_11')}; background: transparent; border: none;")
        self._body.setStyleSheet(
            f"background: {p['bg_content']}; border: 1px solid {p['line']}; "
            f"border-top: none; border-radius: 0 0 4px 4px;"
        )
        self._name_edit.setStyleSheet(_input_style(p))
        self._string_edit.setStyleSheet(_input_style(p))
        self._ref_grid._apply_btn_style()

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._arrow.setText("▾" if self._expanded else "▸")
        self._header.setStyleSheet(_header_style(_p(), self._expanded))

    def _copy_string(self):
        from PyQt6.QtWidgets import QApplication
        text = self._string_edit.text().strip()
        if text:
            QApplication.clipboard().setText(text)

    def _on_name_changed(self, text: str):
        self._name_label.setText(text or self._t.t("artist_name"))
        self.changed.emit()

    def set_entry(self, entry: ArtistEntry):
        self._name_edit.setText(entry.name)
        self._name_label.setText(entry.name or self._t.t("artist_name"))
        self._string_edit.setText(entry.artist_string)
        self._ref_grid.set_paths(entry.reference_images)

    def entry(self) -> ArtistEntry:
        return ArtistEntry(
            name=self._name_edit.text().strip(),
            artist_string=self._string_edit.text().strip(),
            reference_images=self._ref_grid.paths(),
            enabled=True,
        )


# ═══════════════════════════════════════════════════════════
#  OC Banner
# ═══════════════════════════════════════════════════════════

class _OutfitRow(QWidget):
    """A single outfit entry row: toggle + name + tags + delete."""

    changed = pyqtSignal()
    delete_requested = pyqtSignal(object)  # self

    def __init__(self, outfit, parent=None):
        super().__init__(parent)
        p = _p()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # Top row: toggle + name + delete
        top = QHBoxLayout()
        top.setSpacing(6)
        self._toggle = ToggleSwitch(self)
        self._toggle.setChecked(outfit.active)
        self._toggle.toggled.connect(lambda: self.changed.emit())
        top.addWidget(self._toggle)

        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText("outfit name")
        self._name_edit.setText(outfit.name)
        self._name_edit.setStyleSheet(_input_style(p, padding='2px 6px'))
        self._name_edit.setFixedHeight(22)
        self._name_edit.textChanged.connect(lambda: self.changed.emit())
        top.addWidget(self._name_edit, 1)

        del_btn = QPushButton("×", self)
        del_btn.setFixedSize(16, 16)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(_del_btn_style(p, 'fs_10'))
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        top.addWidget(del_btn)
        layout.addLayout(top)

        # Tags row
        self._tags_edit = QLineEdit(self)
        self._tags_edit.setPlaceholderText("school_uniform, pleated_skirt, ...")
        self._tags_edit.setText(outfit.tags)
        self._tags_edit.setStyleSheet(_input_style(p, padding='2px 6px'))
        self._tags_edit.setFixedHeight(22)
        self._tags_edit.textChanged.connect(lambda: self.changed.emit())
        layout.addWidget(self._tags_edit)

    def apply_theme(self):
        p = _p()
        self._name_edit.setStyleSheet(_input_style(p, padding='2px 6px'))
        self._tags_edit.setStyleSheet(_input_style(p, padding='2px 6px'))

    def outfit(self):
        from ..models import OutfitEntry
        return OutfitEntry(
            name=self._name_edit.text().strip(),
            tags=self._tags_edit.text().strip(),
            active=self._toggle.isChecked(),
        )


class OCBanner(QWidget):
    """Expandable entry card for an OC character."""

    changed = pyqtSignal()
    delete_requested = pyqtSignal(object)

    def __init__(self, translator: Translator, storage: AppStorage,
                 entry: OCEntry | None = None, parent=None):
        super().__init__(parent)
        self._t = translator
        self._expanded = False
        p = _p()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        self._header = QWidget(self)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            f"background: {p['bg_surface']}; border: 1px solid {p['line']}; border-radius: 4px;"
        )
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(10, 6, 6, 6)
        hl.setSpacing(8)

        self._arrow = QLabel("▸", self._header)
        self._arrow.setStyleSheet(_arrow_style(p))
        self._arrow.setFixedWidth(10)
        hl.addWidget(self._arrow)

        self._name_label = QLabel(translator.t("character_name"), self._header)
        self._name_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_11')}; background: transparent; border: none;")
        hl.addWidget(self._name_label, 1)

        self._enabled = ToggleSwitch(self._header)
        self._enabled.setChecked(True)
        self._enabled.toggled.connect(lambda: self.changed.emit())
        hl.addWidget(self._enabled)

        del_btn = QPushButton("×", self._header)
        del_btn.setFixedSize(16, 16)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(_del_btn_style(p))
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        hl.addWidget(del_btn)

        self._header.mousePressEvent = lambda e: self._toggle()
        root.addWidget(self._header)

        # ── Body ──
        self._body = QWidget(self)
        self._body.setStyleSheet(
            f"background: {p['bg_content']}; border: 1px solid {p['line']}; "
            f"border-top: none; border-radius: 0 0 4px 4px;"
        )
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(6)

        # Order + Depth row
        spin_style = _input_style(p, padding='2px 4px')
        dim_style = _dim_label_style(p)
        od_row = QHBoxLayout()
        od_row.setSpacing(6)
        od_order_lbl = QLabel("Order", self._body)
        od_order_lbl.setStyleSheet(dim_style)
        od_row.addWidget(od_order_lbl)
        self._order_spin = QSpinBox(self._body)
        self._order_spin.setRange(0, 9999)
        self._order_spin.setValue(100)
        self._order_spin.setFixedWidth(54)
        self._order_spin.setStyleSheet(spin_style)
        self._order_spin.valueChanged.connect(lambda: self.changed.emit())
        od_row.addWidget(self._order_spin)
        od_row.addSpacing(8)
        od_depth_lbl = QLabel("Depth", self._body)
        od_depth_lbl.setStyleSheet(dim_style)
        od_row.addWidget(od_depth_lbl)
        self._depth_spin = QSpinBox(self._body)
        self._depth_spin.setRange(0, 999)
        self._depth_spin.setValue(4)
        self._depth_spin.setFixedWidth(54)
        self._depth_spin.setStyleSheet(spin_style)
        self._depth_spin.valueChanged.connect(lambda: self.changed.emit())
        od_row.addWidget(self._depth_spin)
        od_row.addStretch()
        bl.addLayout(od_row)

        name_lbl = QLabel(translator.t("character_name"), self._body)
        name_lbl.setStyleSheet(dim_style)
        bl.addWidget(name_lbl)
        self._name_edit = QLineEdit(self._body)
        self._name_edit.setStyleSheet(_input_style(p, 'fs_11', '4px 8px'))
        self._name_edit.textChanged.connect(self._on_name_changed)
        bl.addWidget(self._name_edit)

        tags_lbl = QLabel("Tags", self._body)
        tags_lbl.setStyleSheet(dim_style)
        bl.addWidget(tags_lbl)
        self._tags_edit = QTextEdit(self._body)
        self._tags_edit.setStyleSheet(_input_style(p, 'fs_11', '4px 8px'))
        self._tags_edit.setPlaceholderText("1girl, blue_hair, ...")
        self._tags_edit.setMaximumHeight(56)
        self._tags_edit.textChanged.connect(lambda: self.changed.emit())
        bl.addWidget(self._tags_edit)

        self._ref_grid = _RefImageGrid(storage, parent=self._body)
        self._ref_grid.changed.connect(self.changed.emit)
        bl.addWidget(self._ref_grid)

        # ── Outfits section ──
        sep = QLabel("", self._body)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {p['line']}; border: none;")
        bl.addWidget(sep)

        outfit_header = QHBoxLayout()
        outfit_lbl = QLabel("Outfits", self._body)
        outfit_lbl.setStyleSheet(dim_style)
        outfit_header.addWidget(outfit_lbl)
        outfit_header.addStretch()
        add_outfit_btn = QPushButton("+", self._body)
        add_outfit_btn.setFixedSize(20, 20)
        add_outfit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_outfit_btn.setStyleSheet(
            f"background: transparent; color: {p['text_dim']}; border: 1px solid {p['line']}; "
            f"border-radius: 3px; font-size: {_fs('fs_12')};"
        )
        add_outfit_btn.clicked.connect(self._add_outfit)
        outfit_header.addWidget(add_outfit_btn)
        bl.addLayout(outfit_header)

        self._outfit_list = QVBoxLayout()
        self._outfit_list.setSpacing(4)
        bl.addLayout(self._outfit_list)
        self._outfit_rows: list[_OutfitRow] = []

        self._body.hide()
        root.addWidget(self._body)

        if entry:
            self.set_entry(entry)

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._arrow.setText("▾" if self._expanded else "▸")
        self._header.setStyleSheet(_header_style(_p(), self._expanded))

    def apply_theme(self):
        p = _p()
        self._header.setStyleSheet(_header_style(p, self._expanded))
        self._arrow.setStyleSheet(_arrow_style(p))
        self._name_label.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_11')}; background: transparent; border: none;")
        self._body.setStyleSheet(
            f"background: {p['bg_content']}; border: 1px solid {p['line']}; "
            f"border-top: none; border-radius: 0 0 4px 4px;"
        )
        self._name_edit.setStyleSheet(_input_style(p, 'fs_11', '4px 8px'))
        self._tags_edit.setStyleSheet(_input_style(p, 'fs_11', '4px 8px'))
        spin_style = _input_style(p, padding='2px 4px')
        self._order_spin.setStyleSheet(spin_style)
        self._depth_spin.setStyleSheet(spin_style)
        self._ref_grid._apply_btn_style()
        for row in self._outfit_rows:
            row.apply_theme()

    def _on_name_changed(self, text: str):
        self._name_label.setText(text or self._t.t("character_name"))
        self.changed.emit()

    def _add_outfit(self, outfit=None):
        from ..models import OutfitEntry
        if not isinstance(outfit, OutfitEntry):
            outfit = OutfitEntry(name="", tags="")
        row = _OutfitRow(outfit, self)
        row.changed.connect(self.changed.emit)
        row.delete_requested.connect(self._remove_outfit)
        self._outfit_rows.append(row)
        self._outfit_list.addWidget(row)
        self.changed.emit()

    def _remove_outfit(self, row):
        if row in self._outfit_rows:
            self._outfit_rows.remove(row)
            self._outfit_list.removeWidget(row)
            row.deleteLater()
            self.changed.emit()

    def set_entry(self, entry: OCEntry):
        self._name_edit.setText(entry.character_name)
        self._name_label.setText(entry.character_name or self._t.t("character_name"))
        self._tags_edit.setPlainText(entry.tags)
        self._ref_grid.set_paths(entry.reference_images)
        self._order_spin.setValue(entry.order)
        self._depth_spin.setValue(entry.depth)
        self._enabled.setChecked(entry.enabled)
        for o in entry.outfits:
            self._add_outfit(o)

    def entry(self) -> OCEntry:
        from ..models import OutfitEntry
        outfits = [r.outfit() for r in self._outfit_rows]
        return OCEntry(
            character_name=self._name_edit.text().strip(),
            tags=self._tags_edit.toPlainText().strip(),
            reference_images=self._ref_grid.paths(),
            outfits=outfits,
            order=self._order_spin.value(),
            depth=self._depth_spin.value(),
            enabled=self._enabled.isChecked(),
        )


# ═══════════════════════════════════════════════════════════
#  Library Panel — Two-Step Scroll Drawer
# ═══════════════════════════════════════════════════════════

class LibraryPanel(QWidget):
    """Two-step scroll drawer.

    Step 1: Tab button opens a narrow strip (~60px) with section titles.
    Step 2: Click a title → content expands downward with fade animation.
    """

    STRIP_WIDTH = 60
    EXPANDED_WIDTH = 300

    changed = pyqtSignal()
    width_changed = pyqtSignal(int)

    def __init__(self, translator: Translator, storage: AppStorage, parent=None):
        super().__init__(parent)
        self.setObjectName("LibPanel")
        self._t = translator
        self._storage = storage
        self._artist_banners: list[ArtistBanner] = []
        self._oc_banners: list[OCBanner] = []
        self._expanded_section: str | None = None
        self._default_oc_order = 77
        self._default_oc_depth = 4

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Strip (narrow vertical bar with section titles) ──
        self._strip = QWidget(self)
        strip_layout = QVBoxLayout(self._strip)
        strip_layout.setContentsMargins(6, 16, 6, 16)
        strip_layout.setSpacing(8)

        self._artist_title_btn = QPushButton(translator.t("artist_library"), self._strip)
        self._artist_title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._artist_title_btn.clicked.connect(lambda: self._toggle_section(SECTION_ARTIST))
        strip_layout.addWidget(self._artist_title_btn)

        self._oc_title_btn = QPushButton(translator.t("oc_library"), self._strip)
        self._oc_title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._oc_title_btn.clicked.connect(lambda: self._toggle_section(SECTION_OC))
        strip_layout.addWidget(self._oc_title_btn)

        strip_layout.addStretch()
        self._strip.setFixedWidth(self.STRIP_WIDTH)
        root.addWidget(self._strip)

        # ── Content area (shown when a section is selected) ──
        self._content = QWidget(self)
        self._content.hide()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        scroll = QScrollArea(self._content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._scroll_inner = QWidget()
        self._sections_layout = QVBoxLayout(self._scroll_inner)
        self._sections_layout.setContentsMargins(8, 12, 8, 12)
        self._sections_layout.setSpacing(6)

        # Artist content
        self._artist_body = QWidget(self._scroll_inner)
        al = QVBoxLayout(self._artist_body)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        self._artist_list = QVBoxLayout()
        self._artist_list.setSpacing(6)
        al.addLayout(self._artist_list)
        self._add_artist_btn = QPushButton("+ " + translator.t("add_artist"), self._artist_body)
        self._add_artist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_artist_btn.clicked.connect(self._add_artist)
        al.addWidget(self._add_artist_btn)
        al.addStretch()
        self._sections_layout.addWidget(self._artist_body)
        self._artist_body.hide()

        # OC content
        self._oc_body = QWidget(self._scroll_inner)
        ol = QVBoxLayout(self._oc_body)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(6)
        self._oc_list = QVBoxLayout()
        self._oc_list.setSpacing(6)
        ol.addLayout(self._oc_list)
        self._add_oc_btn = QPushButton("+ " + translator.t("add_oc"), self._oc_body)
        self._add_oc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_oc_btn.clicked.connect(self._add_oc)
        ol.addWidget(self._add_oc_btn)
        ol.addStretch()
        self._sections_layout.addWidget(self._oc_body)
        self._oc_body.hide()

        self._sections_layout.addStretch()
        scroll.setWidget(self._scroll_inner)
        cl.addWidget(scroll)
        root.addWidget(self._content, 1)

        self.setMinimumWidth(self.STRIP_WIDTH)
        self.setMaximumWidth(self.STRIP_WIDTH)
        self.apply_theme()

    # ── Section toggle ──

    def _toggle_section(self, section: str):
        if self._expanded_section == section:
            # Collapse — animate width shrink + content fade out
            self._expanded_section = None
            self._apply_strip_styles()
            self._animate_width(self.EXPANDED_WIDTH, self.STRIP_WIDTH, on_finish=self._after_collapse)
        else:
            # Switch or expand
            was_expanded = self._expanded_section is not None
            self._artist_body.setVisible(section == SECTION_ARTIST)
            self._oc_body.setVisible(section == SECTION_OC)
            self._content.show()
            self._expanded_section = section
            self._apply_strip_styles()
            if not was_expanded:
                # Fresh expand — animate width + fade
                self._animate_width(self.STRIP_WIDTH, self.EXPANDED_WIDTH)
                self._fade_content(True)
            else:
                # Switch section — just cross-fade content
                self._fade_content(True)

    def _after_collapse(self):
        self._artist_body.hide()
        self._oc_body.hide()
        self._content.hide()
        self.width_changed.emit(self.width())

    def _animate_width(self, start: int, end: int, on_finish=None):
        # Use fixedWidth via timer steps for smooth resize without dual-property jank
        self._anim_target = end
        anim = QPropertyAnimation(self, b"maximumWidth", self)
        anim.setDuration(200)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumWidth(min(start, end))
        def _on_done():
            self.setMinimumWidth(end)
            self.setMaximumWidth(end)
            self.width_changed.emit(end)
            if on_finish:
                on_finish()
        anim.finished.connect(_on_done)
        anim.valueChanged.connect(lambda: self.width_changed.emit(self.width()))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _fade_content(self, show: bool):
        effect = self._content.graphicsEffect()
        if not effect:
            effect = QGraphicsOpacityEffect(self._content)
            self._content.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(0.0 if show else 1.0)
        anim.setEndValue(1.0 if show else 0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    # ── Theming ──

    def apply_theme(self):
        p = _p()
        self.setStyleSheet(
            f"#LibPanel {{ background: {p['bg']}; border-left: 1px solid {p['line_strong']}; }}"
        )
        self._apply_strip_styles()
        self._apply_add_btn_styles()
        for banner in self._artist_banners:
            banner.apply_theme()
        for banner in self._oc_banners:
            banner.apply_theme()

    def _apply_strip_styles(self):
        p = _p()
        active = (
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: 1px solid {p['accent']}; border-radius: 4px; "
            f"padding: 8px 4px; font-size: {_fs('fs_10')}; font-weight: bold; letter-spacing: 2px;"
        )
        normal = (
            f"background: transparent; color: {p['text_dim']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 8px 4px; font-size: {_fs('fs_10')}; letter-spacing: 2px;"
        )
        hover_extra = f" QPushButton:hover {{ border-color: {p['accent']}; color: {p['text']}; }}"
        self._artist_title_btn.setStyleSheet(
            active if self._expanded_section == SECTION_ARTIST else normal + hover_extra)
        self._oc_title_btn.setStyleSheet(
            active if self._expanded_section == SECTION_OC else normal + hover_extra)

    def _apply_add_btn_styles(self):
        p = _p()
        style = (
            f"background: transparent; color: {p['text_dim']}; "
            f"border: 1px solid {p['line']}; border-radius: 3px; "
            f"padding: 5px 8px; font-size: {_fs('fs_10')}; letter-spacing: 1px;"
        )
        for btn in (self._add_artist_btn, self._add_oc_btn):
            btn.setStyleSheet(style)

    # ── Entry management ──

    def _add_artist(self, entry: ArtistEntry | None = None):
        banner = ArtistBanner(self._t, self._storage, entry, self._scroll_inner)
        banner.changed.connect(self.changed.emit)
        banner.delete_requested.connect(self._remove_artist)
        self._artist_banners.append(banner)
        self._artist_list.addWidget(banner)
        if not entry:
            banner._toggle()
        self.changed.emit()

    def _remove_artist(self, banner):
        if banner in self._artist_banners:
            self._artist_banners.remove(banner)
            self._artist_list.removeWidget(banner)
            banner.deleteLater()
            self.changed.emit()

    def set_oc_defaults(self, order: int, depth: int):
        self._default_oc_order = order
        self._default_oc_depth = depth

    def _add_oc(self, entry: OCEntry | None = None):
        if not isinstance(entry, OCEntry):
            entry = OCEntry(order=self._default_oc_order, depth=self._default_oc_depth)
        banner = OCBanner(self._t, self._storage, entry, self._scroll_inner)
        banner.changed.connect(self.changed.emit)
        banner.delete_requested.connect(self._remove_oc)
        self._oc_banners.append(banner)
        self._oc_list.addWidget(banner)
        if not entry:
            banner._toggle()
        self.changed.emit()

    def _remove_oc(self, banner):
        if banner in self._oc_banners:
            self._oc_banners.remove(banner)
            self._oc_list.removeWidget(banner)
            banner.deleteLater()
            self.changed.emit()

    def set_entries(self, artists: list[ArtistEntry], ocs: list[OCEntry]):
        for a in artists:
            self._add_artist(a)
        for o in ocs:
            self._add_oc(o)

    def artist_entries(self) -> list[ArtistEntry]:
        return [b.entry() for b in self._artist_banners]

    def oc_entries(self) -> list[OCEntry]:
        return [b.entry() for b in self._oc_banners]
