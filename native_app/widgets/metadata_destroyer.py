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
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..metadata import MetadataWriter
from ..theme import _fs, current_palette, is_theme_light
from ..ui_tokens import CLS_METADATA_FRAME, CLS_METADATA_RESULT_ITEM, CLS_METADATA_STATUS_OK, _dp


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
        row.setContentsMargins(_dp(4), 2, _dp(4), 2)
        row.setSpacing(_dp(6))
        if error:
            row.addWidget(QLabel(f"\u2717 {filename} \u2014 {error}", self), 1)
        else:
            lbl = QLabel(f"\u2713 {filename}", self)
            ok_color = '#3a8a48' if is_theme_light() else '#5c5'
            lbl.setStyleSheet(f"color: {ok_color};")
            row.addWidget(lbl, 1)
            copy_btn = QPushButton(translator.t("metadata_copy_file"), self)
            copy_btn.setFixedHeight(_dp(22))
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.clicked.connect(self._copy_file)
            row.addWidget(copy_btn)
            save_btn = QPushButton(translator.t("metadata_save_as"), self)
            save_btn.setFixedHeight(_dp(22))
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
        self._edit_lora_rows: list[tuple[QWidget, QLineEdit, QDoubleSpinBox]] = []

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
        bar_layout.setContentsMargins(_dp(4), _dp(4), _dp(4), _dp(4))
        bar_layout.setSpacing(_dp(6))
        self._single_name_label = QLabel(self._single_bar)
        bar_layout.addWidget(self._single_name_label, 1)
        self._single_edit_btn = QPushButton(self._translator.t("metadata_edit_single"), self._single_bar)
        self._single_edit_btn.setFixedHeight(_dp(22))
        self._single_edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._single_edit_btn.clicked.connect(self._enter_edit_mode)
        bar_layout.addWidget(self._single_edit_btn)
        self._single_close_btn = QPushButton("\u2715", self._single_bar)
        self._single_close_btn.setFixedSize(_dp(22), _dp(22))
        self._single_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._single_close_btn.clicked.connect(self._back_to_empty)
        bar_layout.addWidget(self._single_close_btn)
        self._single_bar.setVisible(False)
        root.addWidget(self._single_bar)

        # Batch results header
        self._batch_header = QWidget(self)
        header_layout = QHBoxLayout(self._batch_header)
        header_layout.setContentsMargins(_dp(4), _dp(4), _dp(4), 0)
        header_layout.setSpacing(_dp(6))
        self._results_label = QLabel(self._batch_header)
        header_layout.addWidget(self._results_label, 1)
        self._save_all_btn = QPushButton(self._translator.t("metadata_save_all"), self._batch_header)
        self._save_all_btn.setFixedHeight(_dp(22))
        self._save_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_all_btn.clicked.connect(self._save_all)
        header_layout.addWidget(self._save_all_btn)
        self._clear_btn = QPushButton(self._translator.t("metadata_clear_results"), self._batch_header)
        self._clear_btn.setFixedHeight(_dp(22))
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
        self._edit_mode = False
        self._preview_label.setVisible(False)
        self._single_bar.setVisible(False)
        self._batch_header.setVisible(False)
        self._scroll.setVisible(False)
        self._clear_result_widgets()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def _clear_result_widgets(self) -> None:
        self._edit_lora_rows = []
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

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
        self._single_edit_btn.setEnabled(False)
        self._single_edit_btn.setVisible(True)
        self._clear_result_widgets()

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
        self._single_edit_btn.setEnabled(True)
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

        if not self._single_src:
            return
        reader = MetadataReader()
        meta = reader.read_metadata(self._single_src)
        if meta is None:
            return
        self._edit_meta = meta
        self._edit_mode = True

        # Hide image preview, show edit UI
        self._preview_label.setVisible(False)
        self._single_edit_btn.setVisible(False)
        self._single_name_label.setText(
            f"{self._translator.t('metadata_edit_mode')} — {self._single_src_name}"
        )

        # Build edit fields in the scroll area
        self._scroll.setVisible(True)
        self._batch_header.setVisible(False)
        self._clear_result_widgets()

        from PyQt6.QtWidgets import QTextEdit
        from ..ui_tokens import CLS_METADATA_TEXT
        from .resize_handle import wrap_with_resize_handle
        # Positive prompt
        self._edit_positive = QTextEdit(self._results_content)
        self._edit_positive.setProperty("class", CLS_METADATA_TEXT)
        self._edit_positive.setPlainText(meta.positive_prompt)
        self._edit_positive.setMaximumHeight(_dp(120))
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
        self._edit_negative.setMaximumHeight(_dp(120))
        neg_container = wrap_with_resize_handle(self._edit_negative, self._results_content)
        neg_section = CollapsibleSection(
            self._translator.t("metadata_negative"),
            neg_container, parent=self._results_content,
        )
        self._results_layout.insertWidget(1, neg_section)

        fields = QWidget(self._results_content)
        grid = QGridLayout(fields)
        grid.setContentsMargins(_dp(4), _dp(4), _dp(4), _dp(4))
        grid.setHorizontalSpacing(_dp(8))
        grid.setVerticalSpacing(_dp(6))
        p = current_palette()
        fields.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_10')};")

        def add_label(row: int, text_key: str) -> QLabel:
            label = QLabel(self._translator.t(text_key), fields)
            label.setStyleSheet(f"color: {p['text_dim']};")
            grid.addWidget(label, row, 0)
            return label

        self._edit_steps = QSpinBox(fields)
        self._edit_steps.setRange(0, 200000)
        self._edit_steps.setValue(_safe_int(meta.parameter("Steps"), 0))
        add_label(0, "metadata_field_steps")
        grid.addWidget(self._edit_steps, 0, 1)

        self._edit_sampler = QLineEdit(meta.parameter("Sampler"), fields)
        add_label(1, "metadata_field_sampler")
        grid.addWidget(self._edit_sampler, 1, 1)

        self._edit_cfg = QDoubleSpinBox(fields)
        self._edit_cfg.setRange(0, 1000)
        self._edit_cfg.setDecimals(3)
        self._edit_cfg.setValue(_safe_float(meta.parameter("CFG scale"), 0.0))
        add_label(2, "metadata_field_cfg")
        grid.addWidget(self._edit_cfg, 2, 1)

        self._edit_seed = QLineEdit(meta.parameter("Seed"), fields)
        add_label(3, "metadata_field_seed")
        grid.addWidget(self._edit_seed, 3, 1)

        size_w, size_h = meta.size_tuple()
        size_row = QWidget(fields)
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        self._edit_width = QSpinBox(size_row)
        self._edit_width.setRange(0, 100000)
        self._edit_width.setValue(size_w)
        self._edit_height = QSpinBox(size_row)
        self._edit_height.setRange(0, 100000)
        self._edit_height.setValue(size_h)
        size_layout.addWidget(self._edit_width)
        size_layout.addWidget(QLabel("x", size_row))
        size_layout.addWidget(self._edit_height)
        add_label(4, "metadata_field_size")
        grid.addWidget(size_row, 4, 1)

        self._edit_model = QLineEdit(meta.parameter("Model") or meta.model_name, fields)
        add_label(5, "metadata_field_model")
        grid.addWidget(self._edit_model, 5, 1)

        params_section = CollapsibleSection(
            self._translator.t("metadata_parameters"),
            fields,
            parent=self._results_content,
        )
        self._results_layout.insertWidget(2, params_section)

        lora_box = QWidget(self._results_content)
        self._lora_layout = QVBoxLayout(lora_box)
        self._lora_layout.setContentsMargins(_dp(4), _dp(4), _dp(4), _dp(4))
        self._lora_layout.setSpacing(_dp(4))
        for item in meta.loras:
            self._add_lora_row(str(item.get("name", "")), str(item.get("weight", "1")))
        add_lora_btn = QPushButton(self._translator.t("metadata_add_lora"), lora_box)
        add_lora_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_lora_btn.clicked.connect(lambda: self._add_lora_row("", "1"))
        self._lora_layout.addWidget(add_lora_btn)
        lora_section = CollapsibleSection(
            self._translator.t("metadata_loras"),
            lora_box,
            parent=self._results_content,
        )
        self._results_layout.insertWidget(3, lora_section)

        # Save button
        save_btn = QPushButton(self._translator.t("metadata_save_copy"), self._results_content)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_edited)
        self._results_layout.insertWidget(4, save_btn)

    def _add_lora_row(self, name: str, weight: str) -> None:
        row = QWidget(self._results_content)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_dp(6))
        name_edit = QLineEdit(name, row)
        name_edit.setPlaceholderText(self._translator.t("metadata_lora_name"))
        weight_spin = QDoubleSpinBox(row)
        weight_spin.setRange(-10, 10)
        weight_spin.setDecimals(3)
        weight_spin.setSingleStep(0.05)
        weight_spin.setValue(_safe_float(weight, 1.0))
        remove_btn = QPushButton("×", row)
        remove_btn.setFixedSize(_dp(22), _dp(22))
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self._remove_lora_row(row))
        layout.addWidget(name_edit, 1)
        layout.addWidget(weight_spin)
        layout.addWidget(remove_btn)
        self._edit_lora_rows.append((row, name_edit, weight_spin))
        insert_at = max(0, self._lora_layout.count() - 1) if hasattr(self, "_lora_layout") else 0
        self._lora_layout.insertWidget(insert_at, row)

    def _remove_lora_row(self, row: QWidget) -> None:
        self._edit_lora_rows = [item for item in self._edit_lora_rows if item[0] is not row]
        row.setParent(None)
        row.deleteLater()

    def _save_edited(self) -> None:
        if not hasattr(self, '_edit_meta') or not self._single_src:
            return
        self._edit_meta.positive_prompt = self._edit_positive.toPlainText()
        self._edit_meta.negative_prompt = self._edit_negative.toPlainText()
        self._edit_meta.set_parameter("Steps", self._edit_steps.value())
        self._edit_meta.set_parameter("Sampler", self._edit_sampler.text())
        self._edit_meta.set_parameter("CFG scale", self._edit_cfg.value())
        self._edit_meta.set_parameter("Seed", self._edit_seed.text())
        self._edit_meta.set_size(self._edit_width.value(), self._edit_height.value())
        self._edit_meta.set_parameter("Model", self._edit_model.text())
        self._edit_meta.model_name = self._edit_model.text().strip()
        self._edit_meta.loras = [
            {"name": name.text().strip(), "weight": f"{weight.value():g}"}
            for _, name, weight in self._edit_lora_rows
            if name.text().strip()
        ]
        self._edit_meta.sync_loras_to_positive_prompt()
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
        self._clear_result_widgets()

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

    def _save_all(self) -> None:
        rows = []
        for i in range(self._results_layout.count()):
            widget = self._results_layout.itemAt(i).widget()
            if isinstance(widget, _ResultRow) and widget._dst_path and os.path.isfile(widget._dst_path):
                rows.append(widget)
        if not rows:
            return
        target_dir = QFileDialog.getExistingDirectory(self, self._translator.t("metadata_save_all"))
        if not target_dir:
            return
        saved = 0
        for row in rows:
            src = row._dst_path
            name = os.path.basename(src)
            dst = _unique_path(os.path.join(target_dir, name))
            shutil.copy2(src, dst)
            saved += 1
        self._results_label.setText(
            self._translator.t("metadata_save_all_done").replace("{count}", str(saved))
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
        self._save_all_btn.setText(self._translator.t("metadata_save_all"))
        self._single_edit_btn.setText(self._translator.t("metadata_edit_single"))
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


def _safe_int(value: str, fallback: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: str, fallback: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _unique_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    candidate = path
    counter = 1
    while os.path.exists(candidate):
        candidate = f"{base}_{counter}{ext}"
        counter += 1
    return candidate
