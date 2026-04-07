from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QThread, QMimeData
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..metadata import MetadataWriter
from ..theme import current_palette, is_theme_light
from ..ui_tokens import CLS_METADATA_FRAME, CLS_METADATA_RESULT_ITEM, CLS_METADATA_STATUS_OK


def _palette() -> dict[str, str]:
    return current_palette()

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class _DraggableImageLabel(QLabel):
    """QLabel that supports dragging the displayed image out (like a browser)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path: str = ""
        self._drag_start = None

    def set_file_path(self, path: str) -> None:
        self._file_path = path

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start is not None
            and self._file_path
            and (event.pos() - self._drag_start).manhattanLength() > 10
        ):
            from PyQt6.QtGui import QDrag
            drag = QDrag(self)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(self._file_path)])
            drag.setMimeData(mime)
            # Set a small thumbnail as drag pixmap
            pm = self.pixmap()
            if pm and not pm.isNull():
                drag.setPixmap(pm.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
            drag.exec(Qt.DropAction.CopyAction)
            self._drag_start = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(event)


class _DestroyWorker(QThread):
    finished = pyqtSignal(str, str, str)

    def __init__(self, writer: MetadataWriter, src: str, dst: str, destroy_text: str | None = None) -> None:
        super().__init__()
        self._writer = writer
        self._src = src
        self._dst = dst
        self._destroy_text = destroy_text

    def run(self) -> None:
        try:
            if Path(self._src).suffix.lower() == ".png":
                self._writer.destroy(self._src, self._dst, text=self._destroy_text)
            else:
                shutil.copy2(self._src, self._dst)
            self.finished.emit(self._src, self._dst, "")
        except Exception as exc:
            self.finished.emit(self._src, "", f"{type(exc).__name__}: {exc}")


class _ResultRow(QWidget):
    def __init__(self, filename: str, dst_path: str, error: str, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", CLS_METADATA_RESULT_ITEM)
        self._dst_path = dst_path
        self._translator = translator
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(6)
        if error:
            row.addWidget(QLabel(f"\u2717 {filename} \u2014 {error}", self), 1)
        else:
            lbl = QLabel(f"\u2713 {filename}", self)
            ok_color = '#3a8a48' if is_theme_light() else '#5c5'
            lbl.setStyleSheet(f"color: {ok_color};")
            row.addWidget(lbl, 1)
            copy_btn = QPushButton(translator.t("metadata_copy_file"), self)
            copy_btn.setFixedHeight(22)
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.clicked.connect(self._copy_file)
            row.addWidget(copy_btn)
            save_btn = QPushButton(translator.t("metadata_save_as"), self)
            save_btn.setFixedHeight(22)
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.clicked.connect(self._save_as)
            row.addWidget(save_btn)

    def _copy_file(self) -> None:
        if self._dst_path and os.path.isfile(self._dst_path):
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(self._dst_path)])
            QApplication.clipboard().setMimeData(mime)

    def _save_as(self) -> None:
        if not self._dst_path or not os.path.isfile(self._dst_path):
            return
        dst, _ = QFileDialog.getSaveFileName(
            self, self._translator.t("metadata_save_as"),
            os.path.basename(self._dst_path), "PNG (*.png);;All (*)",
        )
        if dst:
            shutil.copy2(self._dst_path, dst)


class MetadataDestroyerWidget(QWidget):
    """Metadata destroyer card.

    Three states:
    - Empty: full-area drop zone (click or drag)
    - Single image: shows destroyed image preview, right-click to save/copy
    - Batch: list of results with copy/save buttons per file
    """

    changed = pyqtSignal()
    error_occurred = pyqtSignal(str, str)
    _edit_destroy_preset_requested = pyqtSignal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("class", CLS_METADATA_FRAME)
        self.setAcceptDrops(True)

        self._translator = translator
        self._writer = MetadataWriter()
        self._workers: list[_DestroyWorker] = []
        self._temp_dir = tempfile.mkdtemp(prefix="aitag_destroy_")
        self._destroy_text: str | None = None  # None = use default
        self._state = "empty"  # "empty" | "single" | "batch"
        self._edit_mode = False  # False=destroy, True=edit
        self._single_src: str = ""
        self._single_dst: str = ""
        self._single_src_name: str = ""

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Single image preview (hidden by default, supports drag-out)
        self._preview_label = _DraggableImageLabel(self)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._preview_label.customContextMenuRequested.connect(self._show_single_menu)
        self._preview_label.setVisible(False)
        root.addWidget(self._preview_label, 1)

        # Single image bottom bar
        self._single_bar = QWidget(self)
        bar_layout = QHBoxLayout(self._single_bar)
        bar_layout.setContentsMargins(4, 4, 4, 4)
        bar_layout.setSpacing(6)
        self._single_name_label = QLabel(self._single_bar)
        bar_layout.addWidget(self._single_name_label, 1)
        self._single_close_btn = QPushButton("\u2715", self._single_bar)
        self._single_close_btn.setFixedSize(22, 22)
        self._single_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._single_close_btn.clicked.connect(self._back_to_empty)
        bar_layout.addWidget(self._single_close_btn)
        self._single_bar.setVisible(False)
        root.addWidget(self._single_bar)

        # Batch results header
        self._batch_header = QWidget(self)
        header_layout = QHBoxLayout(self._batch_header)
        header_layout.setContentsMargins(4, 4, 4, 0)
        header_layout.setSpacing(6)
        self._results_label = QLabel(self._batch_header)
        header_layout.addWidget(self._results_label, 1)
        self._clear_btn = QPushButton(self._translator.t("metadata_clear_results"), self._batch_header)
        self._clear_btn.setFixedHeight(22)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._back_to_empty)
        header_layout.addWidget(self._clear_btn)
        self._batch_header.setVisible(False)
        root.addWidget(self._batch_header)

        # Batch scroll area
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._results_content = QWidget()
        self._results_layout = QVBoxLayout(self._results_content)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(2)
        self._results_layout.addStretch()
        self._scroll.setWidget(self._results_content)
        self._scroll.setVisible(False)
        root.addWidget(self._scroll, 1)

    def paintEvent(self, _event) -> None:
        super().paintEvent(_event)
        if self._state != "empty":
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = _palette()
        from PyQt6.QtCore import QRectF
        p.setPen(QPen(QColor(pal['text_dim']), 2, Qt.PenStyle.DashLine))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(8, 8, -8, -8), 8, 8)
        p.setPen(QColor(pal['text_muted']))
        font = p.font()
        font.setPointSize(12)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._translator.t("metadata_drop_to_destroy"))
        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._state == "empty":
            self._pick_files()
        super().mousePressEvent(event)

    def _back_to_empty(self) -> None:
        self._state = "empty"
        self._single_dst = ""
        self._preview_label.setVisible(False)
        self._single_bar.setVisible(False)
        self._batch_header.setVisible(False)
        self._scroll.setVisible(False)
        # Clear batch results
        layout = self._results_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def process_files(self, paths: list[str]) -> None:
        valid = [p for p in paths if os.path.isfile(p) and Path(p).suffix.lower() in _IMAGE_EXTS]
        if not valid:
            return

        if len(valid) == 1:
            self._start_single(valid[0])
        else:
            self._start_batch(valid)

    def _start_single(self, path: str) -> None:
        self._state = "single"
        self._single_src = path
        self._single_src_name = os.path.basename(path)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        fname = os.path.basename(path)
        dst = os.path.join(self._temp_dir, f"destroyed_{fname}")

        self._single_name_label.setText(f"\u27f3 {fname}...")
        self._preview_label.setText("\u27f3")
        self._preview_label.setVisible(True)
        self._single_bar.setVisible(True)
        self._batch_header.setVisible(False)
        self._scroll.setVisible(False)

        worker = _DestroyWorker(self._writer, path, dst, self._destroy_text)
        worker.finished.connect(self._on_single_done)
        self._workers.append(worker)
        worker.start()
        self.update()

    def _on_single_done(self, src: str, dst_path: str, error: str) -> None:
        fname = os.path.basename(src)
        if error:
            self._single_name_label.setText(f"\u2717 {fname}: {error}")
            return
        self._single_dst = dst_path
        self._preview_label.set_file_path(dst_path)
        self._single_name_label.setText(f"\u2713 {fname}")
        pixmap = QPixmap(dst_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self._preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_label.setPixmap(scaled)

    def _show_single_menu(self, pos) -> None:
        menu = QMenu(self)
        if self._single_dst and os.path.isfile(self._single_dst):
            save_action = menu.addAction(self._translator.t("metadata_save_as"))
            copy_action = menu.addAction(self._translator.t("metadata_copy_file"))
        else:
            save_action = copy_action = None
        menu.addSeparator()
        if self._edit_mode:
            mode_action = menu.addAction(self._translator.t("metadata_destroy_mode"))
            edit_preset_action = None
        else:
            edit_sub = menu.addMenu(self._translator.t("metadata_edit_mode"))
            mode_action = edit_sub.addAction(self._translator.t("metadata_edit_single"))
            edit_preset_action = edit_sub.addAction(self._translator.t("metadata_edit_preset"))

        action = menu.exec(self._preview_label.mapToGlobal(pos))
        if action is None:
            return
        if action == save_action:
            dst, _ = QFileDialog.getSaveFileName(
                self, self._translator.t("metadata_save_as"),
                self._single_src_name, "PNG (*.png);;All (*)",
            )
            if dst:
                shutil.copy2(self._single_dst, dst)
        elif action == copy_action:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(self._single_dst)])
            QApplication.clipboard().setMimeData(mime)
        elif action == mode_action:
            if self._edit_mode:
                # Switch back to destroy mode
                self._edit_mode = False
                if self._single_src:
                    self._back_to_empty()
                    self._start_single(self._single_src)
            else:
                # Enter edit mode for single image
                self._edit_mode = True
                if self._single_src:
                    self._enter_edit_mode()
        elif action == edit_preset_action:
            self._edit_destroy_preset_requested.emit()

    def _enter_edit_mode(self) -> None:
        """Show editable metadata fields for the source image."""
        from ..metadata import MetadataReader, ImageMetadata
        from .collapsible_section import CollapsibleSection

        reader = MetadataReader()
        meta = reader.read_metadata(self._single_src)
        if meta is None:
            return
        self._edit_meta = meta

        # Hide image preview, show edit UI
        self._preview_label.setVisible(False)
        self._single_name_label.setText(
            f"{self._translator.t('metadata_edit_mode')} — {self._single_src_name}"
        )

        # Build edit fields in the scroll area
        self._scroll.setVisible(True)
        self._batch_header.setVisible(False)

        from PyQt6.QtWidgets import QTextEdit
        from ..ui_tokens import CLS_METADATA_TEXT
        from .resize_handle import wrap_with_resize_handle
        # Positive prompt
        self._edit_positive = QTextEdit(self._results_content)
        self._edit_positive.setProperty("class", CLS_METADATA_TEXT)
        self._edit_positive.setPlainText(meta.positive_prompt)
        self._edit_positive.setMaximumHeight(120)
        pos_container = wrap_with_resize_handle(self._edit_positive, self._results_content)
        pos_section = CollapsibleSection(
            self._translator.t("metadata_positive"),
            pos_container, parent=self._results_content,
        )
        self._results_layout.insertWidget(0, pos_section)

        # Negative prompt
        self._edit_negative = QTextEdit(self._results_content)
        self._edit_negative.setProperty("class", CLS_METADATA_TEXT)
        self._edit_negative.setPlainText(meta.negative_prompt)
        self._edit_negative.setMaximumHeight(120)
        neg_container = wrap_with_resize_handle(self._edit_negative, self._results_content)
        neg_section = CollapsibleSection(
            self._translator.t("metadata_negative"),
            neg_container, parent=self._results_content,
        )
        self._results_layout.insertWidget(1, neg_section)

        # Save button
        save_btn = QPushButton(self._translator.t("metadata_save_copy"), self._results_content)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_edited)
        self._results_layout.insertWidget(2, save_btn)

    def _save_edited(self) -> None:
        if not hasattr(self, '_edit_meta') or not self._single_src:
            return
        self._edit_meta.positive_prompt = self._edit_positive.toPlainText()
        self._edit_meta.negative_prompt = self._edit_negative.toPlainText()
        dst, _ = QFileDialog.getSaveFileName(
            self, self._translator.t("metadata_save_copy"),
            os.path.splitext(self._single_src_name)[0] + "_edited.png",
            "PNG (*.png)",
        )
        if dst:
            self._writer.edit(self._single_src, dst, self._edit_meta)

    def _start_batch(self, paths: list[str]) -> None:
        self._state = "batch"
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._preview_label.setVisible(False)
        self._single_bar.setVisible(False)
        self._batch_header.setVisible(True)
        self._scroll.setVisible(True)

        for path in paths:
            fname = os.path.basename(path)
            dst = os.path.join(self._temp_dir, f"destroyed_{fname}")
            busy = QLabel(f"\u27f3 {fname}...", self._results_content)
            self._results_layout.insertWidget(self._results_layout.count() - 1, busy)
            worker = _DestroyWorker(self._writer, path, dst, self._destroy_text)
            worker.finished.connect(
                lambda s, d, e, lbl=busy: self._on_batch_done(s, d, e, lbl)
            )
            self._workers.append(worker)
            worker.start()
        self._update_batch_header()
        self.update()

    def _on_batch_done(self, src: str, dst_path: str, error: str, busy_label: QLabel) -> None:
        busy_label.setParent(None)
        busy_label.deleteLater()
        row = _ResultRow(os.path.basename(src), dst_path, error, self._translator, self._results_content)
        self._results_layout.insertWidget(self._results_layout.count() - 1, row)
        self._update_batch_header()

    def _update_batch_header(self) -> None:
        count = self._results_layout.count() - 1
        self._results_label.setText(
            self._translator.t("metadata_destroy_results").replace("{count}", str(count))
        )

    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, self._translator.t("select_image"), "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if paths:
            self.process_files(paths)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in _IMAGE_EXTS:
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if Path(url.toLocalFile()).suffix.lower() in _IMAGE_EXTS]
        if paths:
            self.process_files(paths)

    def retranslate_ui(self) -> None:
        self._clear_btn.setText(self._translator.t("metadata_clear_results"))
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Refresh single image preview on resize
        if self._state == "single" and self._single_dst and os.path.isfile(self._single_dst):
            pixmap = QPixmap(self._single_dst)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self._preview_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._preview_label.setPixmap(scaled)

    def cleanup_temp(self) -> None:
        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass
