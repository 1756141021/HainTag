from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..file_filters import image_filter
from ..metadata import MetadataReader, ImageMetadata
from ..theme import current_palette
from ..ui_tokens import CLS_FIELD_LABEL, CLS_METADATA_FRAME, CLS_METADATA_TEXT, _dp
from .collapsible_section import CollapsibleSection
from .text_context_menu import install_localized_context_menus


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class _DropZonePage(QWidget):
    """Full-area drop zone / click target — the empty state."""

    clicked = pyqtSignal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pal = current_palette()
        from PyQt6.QtGui import QColor, QPen
        from PyQt6.QtCore import QRectF

        pen = QPen(QColor(pal['text_dim']), 2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        r = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        p.drawRoundedRect(r, 8, 8)

        p.setPen(QColor(pal['text_muted']))
        font = p.font()
        font.setPointSize(13)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._translator.t("metadata_drop_hint"))
        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in _IMAGE_EXTS:
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent) -> None:
        event.acceptProposedAction()
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in _IMAGE_EXTS:
                # Bubble up to parent
                parent = self.parent()
                while parent and not isinstance(parent, MetadataViewerWidget):
                    parent = parent.parent()
                if parent:
                    parent.load_image(path)
                break


class MetadataViewerWidget(QWidget):
    """Metadata viewer card.

    Two states:
    - Empty: full-area drop zone with centered hint text (click or drag).
    - Loaded: thumbnail + parsed metadata sections with collapse support.
    """

    changed = pyqtSignal()
    close_requested = pyqtSignal()
    error_occurred = pyqtSignal(str, str)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("class", CLS_METADATA_FRAME)
        self.setAcceptDrops(True)

        self._translator = translator
        self._reader = MetadataReader()
        self._metadata: ImageMetadata | None = None
        self._image_path: str = ""

        self._build_ui()

    def _build_ui(self) -> None:
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        # Page 0: Drop zone (empty state)
        self._drop_page = _DropZonePage(self._translator, self)
        self._drop_page.clicked.connect(self._pick_file)
        self._stack.addWidget(self._drop_page)

        # Page 1: Content (loaded state)
        self._content_page = QWidget(self)
        content_root = QVBoxLayout(self._content_page)
        content_root.setContentsMargins(0, 0, 0, 0)
        content_root.setSpacing(_dp(6))

        # Top bar: thumbnail + file info + close button
        top_row = QHBoxLayout()
        top_row.setSpacing(_dp(8))

        self._thumbnail = QLabel(self._content_page)
        self._thumbnail.setFixedSize(_dp(80), _dp(80))
        self._thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p = current_palette()
        self._thumbnail.setStyleSheet(f"border: 1px solid {p['line']}; border-radius: 4px;")
        top_row.addWidget(self._thumbnail)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self._file_label = QLabel(self._content_page)
        self._file_label.setProperty("class", CLS_FIELD_LABEL)
        self._file_label.setWordWrap(True)
        info_col.addWidget(self._file_label)

        self._generator_label = QLabel(self._content_page)
        self._generator_label.setProperty("class", CLS_FIELD_LABEL)
        info_col.addWidget(self._generator_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(_dp(4))
        self._change_btn = QPushButton(self._translator.t("metadata_change_file"), self._content_page)
        self._change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._change_btn.clicked.connect(self._pick_file)
        self._change_btn.setFixedHeight(_dp(22))
        btn_row.addWidget(self._change_btn)

        self._close_btn = QPushButton("✕", self._content_page)
        self._close_btn.setFixedSize(_dp(22), _dp(22))
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip(self._translator.t("close"))
        self._close_btn.clicked.connect(self._back_to_empty)
        btn_row.addWidget(self._close_btn)
        btn_row.addStretch()
        info_col.addLayout(btn_row)

        info_col.addStretch()
        top_row.addLayout(info_col, 1)
        content_root.addLayout(top_row)

        # Scrollable metadata sections
        scroll = QScrollArea(self._content_page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_content = QWidget()
        self._sections_layout = QVBoxLayout(self._scroll_content)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(_dp(4))
        scroll.setWidget(self._scroll_content)
        content_root.addWidget(scroll, 1)

        content_root.addStretch(0)

        self._stack.addWidget(self._content_page)

        # Start on drop zone
        self._stack.setCurrentIndex(0)

    def _back_to_empty(self) -> None:
        self._metadata = None
        self._image_path = ""
        self._clear_sections()
        self._stack.setCurrentIndex(0)

    def load_image(self, path: str) -> None:
        if not os.path.isfile(path):
            return

        self._image_path = path
        self._metadata = self._reader.read_metadata(path)

        # Switch to content page
        self._stack.setCurrentIndex(1)

        # Thumbnail
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self._thumbnail.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumbnail.setPixmap(scaled)
        else:
            self._thumbnail.clear()

        # File info
        self._file_label.setText(os.path.basename(path))

        if self._metadata is None:
            self._generator_label.setText(self._translator.t("metadata_none_found"))
            self._clear_sections()
            return

        meta = self._metadata
        try:
            from PIL import Image
            with Image.open(path) as img:
                w, h = img.size
            size_str = f"{w}\u00d7{h}"
        except Exception:
            size_str = ""

        info_parts = [meta.generator.value.upper()]
        if meta.model_name:
            info_parts.append(meta.model_name)
        if size_str:
            info_parts.append(size_str)
        self._generator_label.setText("  |  ".join(info_parts))

        self._populate_sections(meta)

    def _populate_sections(self, meta: ImageMetadata) -> None:
        self._clear_sections()
        layout = self._sections_layout

        if meta.positive_prompt:
            text_edit = self._make_text_display(meta.positive_prompt)
            copy_btn = self._make_copy_btn(lambda: self._copy_text(meta.positive_prompt))
            section = CollapsibleSection(
                self._translator.t("metadata_positive"), text_edit,
                right_widget=copy_btn, parent=self._scroll_content,
            )
            layout.addWidget(section)

        if meta.negative_prompt:
            text_edit = self._make_text_display(meta.negative_prompt)
            copy_btn = self._make_copy_btn(lambda: self._copy_text(meta.negative_prompt))
            section = CollapsibleSection(
                self._translator.t("metadata_negative"), text_edit,
                right_widget=copy_btn, parent=self._scroll_content,
            )
            layout.addWidget(section)

        if meta.parameters:
            params_text = "\n".join(f"{k}: {v}" for k, v in meta.parameters.items())
            section = CollapsibleSection(
                self._translator.t("metadata_parameters"),
                self._make_text_display(params_text),
                parent=self._scroll_content,
            )
            layout.addWidget(section)

        if meta.loras:
            lines = []
            for lora in meta.loras:
                line = f"{lora.get('name', '')} ({lora.get('weight', '')})"
                h = lora.get("hash", "")
                if h:
                    line += f"  [{h}]"
                lines.append(line)
            lora_fmt = " ".join(f"<lora:{l.get('name', '')}:{l.get('weight', '1')}>" for l in meta.loras)
            copy_lora_btn = self._make_copy_btn(lambda: self._copy_text(lora_fmt))
            section = CollapsibleSection(
                f"LoRA ({len(meta.loras)})",
                self._make_text_display("\n".join(lines)),
                right_widget=copy_lora_btn,
                parent=self._scroll_content,
            )
            layout.addWidget(section)

        if meta.workflow_json:
            preview = meta.workflow_json[:200] + "..." if len(meta.workflow_json) > 200 else meta.workflow_json
            section = CollapsibleSection(
                f"Workflow ({len(meta.workflow_json):,} chars)",
                self._make_text_display(preview),
                collapsed=True, parent=self._scroll_content,
            )
            layout.addWidget(section)

        raw_keys = [k for k in meta.raw_chunks if k not in ("parameters", "workflow", "prompt")]
        if raw_keys:
            lines = []
            for k in raw_keys:
                v = meta.raw_chunks[k]
                if len(v) > 100:
                    v = v[:100] + "..."
                lines.append(f"{k}: {v}")
            section = CollapsibleSection(
                self._translator.t("metadata_raw_chunks"),
                self._make_text_display("\n".join(lines)),
                collapsed=True, parent=self._scroll_content,
            )
            layout.addWidget(section)

        layout.addStretch()

    def _clear_sections(self) -> None:
        layout = self._sections_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _make_text_display(self, text: str) -> QWidget:
        from .resize_handle import wrap_with_resize_handle
        edit = QTextEdit(self._scroll_content)
        edit.setProperty("class", CLS_METADATA_TEXT)
        edit.setPlainText(text)
        edit.setReadOnly(True)
        edit.setMaximumHeight(_dp(120))
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        install_localized_context_menus(edit, self._translator)
        return wrap_with_resize_handle(edit, self._scroll_content)

    def _make_copy_btn(self, callback) -> QPushButton:
        btn = QPushButton(self._translator.t("copy"), self._scroll_content)
        btn.setFixedHeight(_dp(20))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    def _pick_file(self) -> None:
        from ..file_dialogs import pick_image_file
        path = pick_image_file(self, self._translator)
        if path:
            self.load_image(path)


    # Drag and drop (for content page — drop zone page handles its own)
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in _IMAGE_EXTS:
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in _IMAGE_EXTS:
                self.load_image(path)
                break

    def retranslate_ui(self) -> None:
        self._drop_page.update()
        if self._metadata:
            self._change_btn.setText(self._translator.t("metadata_change_file"))
            self._close_btn.setToolTip(self._translator.t("close"))
