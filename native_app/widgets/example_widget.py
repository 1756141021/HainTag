from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..file_filters import image_filter
from ..models import ExampleEntry
from ..storage import AppStorage
from ..theme import _fs, current_palette
from ..ui_tokens import (
    CLS_EXAMPLE_DELETE_BUTTON,
    CLS_EXAMPLE_FRAME,
    CLS_EXAMPLE_TEXT,
    CLS_FIELD_LABEL,
    CLS_FIELD_SPIN,
    CLS_IMAGE_SELECT_BUTTON,
    _dp,
)
from .text_context_menu import install_localized_context_menus


class ExampleWidget(QWidget):
    changed = pyqtSignal()
    delete_requested = pyqtSignal(object)
    error_occurred = pyqtSignal(str, str)

    def __init__(self, translator: Translator, storage: AppStorage, entry: ExampleEntry, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", CLS_EXAMPLE_FRAME)
        self._translator = translator
        self._storage = storage
        self._image_path = entry.image_path

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(_dp(8))

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(_dp(8))

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(_dp(6))
        form.setVerticalSpacing(_dp(6))

        self.order_label = QLabel(self)
        self.order_label.setProperty("class", CLS_FIELD_LABEL)
        self.order_spin = QSpinBox(self)
        self.order_spin.setRange(0, 9999)
        self.order_spin.setProperty("class", CLS_FIELD_SPIN)
        self.order_spin.setValue(entry.order)
        self.order_spin.setToolTip(translator.t("tip_order"))
        self.order_spin.valueChanged.connect(self.changed)
        form.addRow(self.order_label, self.order_spin)

        self.depth_label_inline = QLabel(self)
        self.depth_label_inline.setProperty("class", CLS_FIELD_LABEL)
        self.depth_spin = QSpinBox(self)
        self.depth_spin.setRange(0, 999)
        self.depth_spin.setProperty("class", CLS_FIELD_SPIN)
        self.depth_spin.setValue(entry.depth)
        self.depth_spin.setToolTip(translator.t("tip_depth"))
        self.depth_spin.valueChanged.connect(self.changed)
        form.addRow(self.depth_label_inline, self.depth_spin)
        top_row.addLayout(form)

        self.image_button = QPushButton(self)
        self.image_button.setProperty("class", CLS_IMAGE_SELECT_BUTTON)
        self.image_button.setFixedSize(_dp(112), _dp(112))
        self.image_button.clicked.connect(self._select_image)
        top_row.addWidget(self.image_button)

        self.delete_button = QPushButton("×", self)
        self.delete_button.setProperty("class", CLS_EXAMPLE_DELETE_BUTTON)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self))
        top_row.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignTop)

        root.addLayout(top_row)

        self.tags_label = QLabel(self)
        self.tags_label.setProperty("class", CLS_FIELD_LABEL)
        root.addWidget(self.tags_label)

        from .resize_handle import wrap_with_resize_handle
        self.tags_edit = QTextEdit(self)
        self.tags_edit.setProperty("class", CLS_EXAMPLE_TEXT)
        self.tags_edit.setMaximumHeight(_dp(92))
        self.tags_edit.setPlainText(entry.tags)
        self.tags_edit.textChanged.connect(self.changed)
        root.addWidget(wrap_with_resize_handle(self.tags_edit, self))

        self.description_label = QLabel(self)
        self.description_label.setProperty("class", CLS_FIELD_LABEL)
        root.addWidget(self.description_label)

        self.description_edit = QTextEdit(self)
        self.description_edit.setProperty("class", CLS_EXAMPLE_TEXT)
        self.description_edit.setMaximumHeight(_dp(108))
        self.description_edit.setPlainText(entry.description)
        self.description_edit.textChanged.connect(self.changed)
        root.addWidget(wrap_with_resize_handle(self.description_edit, self))

        # Warning when incomplete
        self._warning_label = QLabel(self)
        p = current_palette()
        self._warning_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; border: none; background: transparent;")
        self._warning_label.hide()
        root.addWidget(self._warning_label)
        self.tags_edit.textChanged.connect(self._check_completeness)
        self.description_edit.textChanged.connect(self._check_completeness)

        self._tag_dictionary = None
        self.retranslate_ui()
        self._refresh_image_preview()
        install_localized_context_menus(self, translator)

    def set_tag_dictionary(self, dictionary) -> None:
        from .tag_completer import install_completer_recursive
        self._tag_dictionary = dictionary
        install_completer_recursive(self, dictionary)

    def _select_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.t("select_image"),
            "",
            image_filter(self._translator),
        )
        if not file_path:
            return

        # Extract metadata from the original file before copying
        extracted_tags = ""
        try:
            from ..metadata import MetadataReader
            meta = MetadataReader().read_metadata(file_path)
            if meta and meta.positive_prompt:
                extracted_tags = meta.positive_prompt
        except Exception:
            pass

        try:
            if self._image_path:
                self._storage.remove_example_image(self._image_path)
            self._image_path = self._storage.copy_example_image(file_path)
        except Exception as exc:
            self.error_occurred.emit(
                self._translator.t("error_example_image_failed"),
                f"{type(exc).__name__}: {exc}",
            )
            return

        # Auto-fill tags if currently empty and metadata was found
        if extracted_tags and not self.tags_edit.toPlainText().strip():
            self.tags_edit.setPlainText(extracted_tags)

        self._refresh_image_preview()
        self.changed.emit()

    def _refresh_image_preview(self) -> None:
        if self._image_path and Path(self._image_path).exists():
            pixmap = QPixmap(self._image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.image_button.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_button.setIcon(QIcon(scaled))
                self.image_button.setIconSize(self.image_button.size())
                self.image_button.setText("")
                return
        self.image_button.setIcon(QIcon())
        self.image_button.setText(self._translator.t("select_image"))

    def entry(self) -> ExampleEntry:
        return ExampleEntry(
            image_path=self._image_path,
            tags=self.tags_edit.toPlainText(),
            description=self.description_edit.toPlainText(),
            order=int(self.order_spin.value()),
            depth=int(self.depth_spin.value()),
        )

    def remove_assets(self) -> None:
        if self._image_path:
            self._storage.remove_example_image(self._image_path)

    def _check_completeness(self) -> None:
        has_tags = bool(self.tags_edit.toPlainText().strip())
        has_desc = bool(self.description_edit.toPlainText().strip())
        if has_tags != has_desc:
            missing = self._translator.t("description") if has_tags else self._translator.t("tags")
            self._warning_label.setText(f"⚠ {self._translator.t('example_incomplete').replace('{field}', missing)}")
            self._warning_label.show()
        else:
            self._warning_label.hide()

    def retranslate_ui(self) -> None:
        self.order_label.setText(self._translator.t("order"))
        self.depth_label_inline.setText(self._translator.t("depth"))
        self.tags_label.setText(self._translator.t("tags"))
        self.description_label.setText(self._translator.t("description"))
        self.tags_edit.setPlaceholderText(self._translator.t("tags_placeholder"))
        self.description_edit.setPlaceholderText(self._translator.t("description"))
        self.delete_button.setToolTip(self._translator.t("delete"))
        self._refresh_image_preview()
