from __future__ import annotations

from functools import partial

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..models import (
    AppSettings,
    SEND_MODE_CTRL_ENTER,
    SEND_MODE_ENTER,
    CONFIG_FINE_SCOPES,
    CONFIG_SCOPE_APPEARANCE,
    CONFIG_SCOPE_ARTIST_LIBRARY,
    CONFIG_SCOPE_ENTRY_DEFAULTS,
    CONFIG_SCOPE_EXAMPLES,
    CONFIG_SCOPE_HISTORY,
    CONFIG_SCOPE_MODEL_PARAMS,
    CONFIG_SCOPE_OC_LIBRARY,
    CONFIG_SCOPE_PROMPTS,
    CONFIG_SCOPE_TAG_MARKERS,
    CONFIG_SCOPE_WINDOW_LAYOUT,
)
from ..ui_tokens import (
    CLS_FIELD_COMBO,
    CLS_FIELD_INPUT,
    CLS_FIELD_LABEL,
    CLS_FIELD_SPIN,
    CLS_SLIDER_VALUE,
    CLS_SUMMARY_TEXT,
    SETTINGS_WIDTH,
    _dp,
)
from .common import ToggleSwitch


class SettingsPanel(QWidget):
    settings_changed = pyqtSignal()
    language_changed = pyqtSignal(str)
    export_prompts_requested = pyqtSignal()
    import_prompts_requested = pyqtSignal()
    config_export_requested = pyqtSignal(list)
    config_import_requested = pyqtSignal(list)
    fetch_models_requested = pyqtSignal()

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._open = False
        self._target_width = _dp(SETTINGS_WIDTH)
        self._ui_scale_percent = 100
        self._body_font_point_size = 11
        self._font_profile = 'default'
        self._custom_font_id = ''
        self.setObjectName('SettingsPanel')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QLabel(self)
        header.setObjectName('PanelHeader')
        header.setContentsMargins(_dp(16), _dp(12), _dp(16), _dp(12))
        self.header_label = header
        root.addWidget(header)

        scroller = QScrollArea(self)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroller, 1)

        body = QWidget(scroller)
        scroller.setWidget(body)
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(_dp(16), _dp(8), _dp(16), _dp(16))
        self.body_layout.setSpacing(_dp(10))

        self.language_label = self._add_label(body)
        self.language_combo = QComboBox(body)
        self.language_combo.setProperty('class', CLS_FIELD_COMBO)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.body_layout.addWidget(self.language_combo)

        self.send_mode_label = self._add_label(body)
        self.send_mode_combo = QComboBox(body)
        self.send_mode_combo.setProperty('class', CLS_FIELD_COMBO)
        self.send_mode_combo.currentIndexChanged.connect(self.settings_changed)
        self.body_layout.addWidget(self.send_mode_combo)

        self.api_label = self._add_label(body)
        self.api_base_url = self._add_line_edit(body, 'https://api.openai.com/v1')

        self.api_key_label = self._add_label(body)
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.setSpacing(_dp(6))
        self.api_key = QLineEdit(body)
        self.api_key.setProperty('class', CLS_FIELD_INPUT)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.textChanged.connect(self.settings_changed)
        key_row.addWidget(self.api_key, 1)
        self.eye_button = QPushButton('◉', body)
        self.eye_button.setObjectName('SecondaryButton')
        self.eye_button.setFixedWidth(_dp(36))
        self.eye_button.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.eye_button)
        self.body_layout.addLayout(key_row)
        self._key_visible = False

        self.model_label = self._add_label(body)
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(_dp(6))
        self.model_combo = QComboBox(body)
        self.model_combo.setEditable(True)
        self.model_combo.setProperty('class', CLS_FIELD_COMBO)
        self.model_combo.setCurrentText('gpt-4o')
        self.model_combo.currentTextChanged.connect(self.settings_changed)
        model_row.addWidget(self.model_combo, 1)
        self.fetch_models_button = QPushButton('↻', body)
        self.fetch_models_button.setObjectName('SecondaryButton')
        self.fetch_models_button.setFixedWidth(_dp(36))
        self.fetch_models_button.clicked.connect(self.fetch_models_requested)
        model_row.addWidget(self.fetch_models_button)
        self.body_layout.addLayout(model_row)

        self.temperature_slider, self.temperature_value, self.temperature_label = self._add_slider(body, 0, 20, 10)
        self.top_p_slider, self.top_p_value, self.top_p_label = self._add_slider(body, 0, 100, 100)

        self.top_k_label = self._add_label(body)
        self.top_k_spin = QSpinBox(body)
        self.top_k_spin.setProperty('class', CLS_FIELD_SPIN)
        self.top_k_spin.setRange(-1, 2000)
        self.top_k_spin.setSpecialValueText('--')
        self.top_k_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.top_k_spin.wheelEvent = lambda e: e.ignore()
        self.top_k_spin.valueChanged.connect(self.settings_changed)
        self.body_layout.addWidget(self.top_k_spin)

        self.freq_slider, self.freq_value, self.freq_label = self._add_slider(body, -20, 20, 0)
        self.pres_slider, self.pres_value, self.pres_label = self._add_slider(body, -20, 20, 0)

        self.max_tokens_label = self._add_label(body)
        self.max_tokens_spin = QSpinBox(body)
        self.max_tokens_spin.setProperty('class', CLS_FIELD_SPIN)
        self.max_tokens_spin.setRange(1, 200000)
        self.max_tokens_spin.setValue(2048)
        self.max_tokens_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.max_tokens_spin.wheelEvent = lambda e: e.ignore()
        self.max_tokens_spin.valueChanged.connect(self.settings_changed)
        self.body_layout.addWidget(self.max_tokens_spin)

        self.stream_label, self.stream_toggle = self._add_toggle_row(body)
        self.memory_label, self.memory_toggle = self._add_toggle_row(body)

        self.history_retention_label = self._add_label(body)
        self.history_retention_combo = QComboBox(body)
        self.history_retention_combo.setProperty('class', CLS_FIELD_COMBO)
        self.history_retention_combo.currentIndexChanged.connect(self.settings_changed)
        self.body_layout.addWidget(self.history_retention_combo)

        self.summary_prompt_label = self._add_label(body)
        self.summary_prompt_edit = QTextEdit(body)
        self.summary_prompt_edit.setProperty('class', CLS_SUMMARY_TEXT)
        self.summary_prompt_edit.setMinimumHeight(_dp(120))
        self.summary_prompt_edit.textChanged.connect(self.settings_changed)
        self.body_layout.addWidget(self.summary_prompt_edit)

        # ── Entry defaults — compact inline rows ──
        self.defaults_label = self._add_label(body)

        def _default_spin(val, max_val):
            s = QSpinBox(body)
            s.setProperty('class', CLS_FIELD_SPIN)
            s.setRange(0, max_val)
            s.setValue(val)
            s.setFixedWidth(_dp(52))
            s.valueChanged.connect(self.settings_changed)
            return s

        self._default_field_labels: dict[str, QLabel] = {}

        def _inline_row(label_key, spin):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(_dp(6))
            lbl = QLabel(self._translator.t(label_key), body)
            lbl.setProperty('class', CLS_FIELD_LABEL)
            lbl.setFixedWidth(_dp(90))
            self._default_field_labels[label_key] = lbl
            row.addWidget(lbl)
            row.addWidget(spin)
            row.addStretch()
            return row

        self._def_example_order = _default_spin(50, 9999)
        self._def_example_depth = _default_spin(4, 999)
        self._def_oc_order = _default_spin(77, 9999)
        self._def_oc_depth = _default_spin(4, 999)

        self.body_layout.addLayout(_inline_row("default_example_order", self._def_example_order))
        self.body_layout.addLayout(_inline_row("default_example_depth", self._def_example_depth))
        self.body_layout.addLayout(_inline_row("default_oc_order", self._def_oc_order))
        self.body_layout.addLayout(_inline_row("default_oc_depth", self._def_oc_depth))

        # ── TAG extraction markers ──
        self.markers_label = self._add_label(body)

        def _marker_row(label_start, label_end, default_start, default_end):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(_dp(4))
            start_edit = QLineEdit(body)
            start_edit.setProperty('class', CLS_FIELD_INPUT)
            start_edit.setText(default_start)
            start_edit.setFixedWidth(_dp(80))
            start_edit.setPlaceholderText(label_start)
            start_edit.textChanged.connect(self.settings_changed)
            end_edit = QLineEdit(body)
            end_edit.setProperty('class', CLS_FIELD_INPUT)
            end_edit.setText(default_end)
            end_edit.setFixedWidth(_dp(80))
            end_edit.setPlaceholderText(label_end)
            end_edit.textChanged.connect(self.settings_changed)
            lbl = QLabel(label_start, body)
            lbl.setProperty('class', CLS_FIELD_LABEL)
            lbl.setFixedWidth(_dp(70))
            row.addWidget(lbl)
            row.addWidget(start_edit)
            row.addWidget(end_edit)
            row.addStretch()
            return row, start_edit, end_edit

        row_full, self._tag_full_start, self._tag_full_end = _marker_row(
            "Full TAG", "end", "[TAGS]", "[/TAGS]")
        self._tag_full_start.setToolTip(self._translator.t('tip_tag_full'))
        self._tag_full_end.setToolTip(self._translator.t('tip_tag_full'))
        row_nochar, self._tag_nochar_start, self._tag_nochar_end = _marker_row(
            "No-char", "end", "[NOTAGS]", "[/NOTAGS]")
        self._tag_nochar_start.setToolTip(self._translator.t('tip_tag_nochar'))
        self._tag_nochar_end.setToolTip(self._translator.t('tip_tag_nochar'))
        self.body_layout.addLayout(row_full)
        self.body_layout.addLayout(row_nochar)

        io_row = QHBoxLayout()
        io_row.setContentsMargins(0, 0, 0, 0)
        io_row.setSpacing(_dp(8))
        self.export_button = QPushButton(body)
        self.export_button.setObjectName('SecondaryButton')
        self.export_button.clicked.connect(self._show_export_menu)
        io_row.addWidget(self.export_button)
        self.import_button = QPushButton(body)
        self.import_button.setObjectName('SecondaryButton')
        self.import_button.clicked.connect(self._show_import_menu)
        io_row.addWidget(self.import_button)
        self.body_layout.addLayout(io_row)

        # Check for Updates button
        self.check_update_button = QPushButton(parent)
        self.check_update_button.setObjectName('SecondaryButton')
        self.check_update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.body_layout.addWidget(self.check_update_button)

        self.body_layout.addStretch(1)

        self._slider_meta = {
            self.temperature_slider: (self.temperature_value, 0.1, 1),
            self.top_p_slider: (self.top_p_value, 0.01, 2),
            self.freq_slider: (self.freq_value, 0.1, 1),
            self.pres_slider: (self.pres_value, 0.1, 1),
        }
        for slider in self._slider_meta:
            slider.valueChanged.connect(partial(self._sync_slider_label, slider))
            slider.valueChanged.connect(self.settings_changed)

        self.stream_toggle.toggled.connect(self.settings_changed)
        self.memory_toggle.toggled.connect(self.settings_changed)
        self._tag_dictionary = None
        self.retranslate_ui()

    def set_tag_dictionary(self, dictionary) -> None:
        from .tag_completer import install_completer_recursive
        self._tag_dictionary = dictionary
        install_completer_recursive(self, dictionary)

    def _add_label(self, parent: QWidget) -> QLabel:
        label = QLabel(parent)
        label.setProperty('class', CLS_FIELD_LABEL)
        self.body_layout.addWidget(label)
        return label

    def _add_line_edit(self, parent: QWidget, placeholder: str) -> QLineEdit:
        line_edit = QLineEdit(parent)
        line_edit.setProperty('class', CLS_FIELD_INPUT)
        line_edit.setPlaceholderText(placeholder)
        line_edit.textChanged.connect(self.settings_changed)
        self.body_layout.addWidget(line_edit)
        return line_edit

    def _add_slider(self, parent: QWidget, minimum: int, maximum: int, default: int) -> tuple[QSlider, QLabel, QLabel]:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_dp(6))
        label = QLabel(parent)
        label.setProperty('class', CLS_FIELD_LABEL)
        row.addWidget(label)
        row.addStretch(1)
        value_label = QLabel(parent)
        value_label.setProperty('class', CLS_SLIDER_VALUE)
        row.addWidget(value_label)
        self.body_layout.addLayout(row)
        slider = QSlider(Qt.Orientation.Horizontal, parent)
        slider.setRange(minimum, maximum)
        slider.setValue(default)
        slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        slider.wheelEvent = lambda e: e.ignore()
        self.body_layout.addWidget(slider)
        return slider, value_label, label

    def _add_toggle_row(self, parent: QWidget) -> tuple[QLabel, ToggleSwitch]:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_dp(8))
        label = QLabel(parent)
        label.setProperty('class', CLS_FIELD_LABEL)
        row.addWidget(label)
        row.addStretch(1)
        toggle = ToggleSwitch(parent)
        row.addWidget(toggle)
        self.body_layout.addLayout(row)
        return label, toggle

    def _sync_slider_label(self, slider: QSlider) -> None:
        label, step, digits = self._slider_meta[slider]
        label.setText(f'{slider.value() * step:.{digits}f}')

    def _toggle_key_visibility(self) -> None:
        self._key_visible = not self._key_visible
        self.api_key.setEchoMode(QLineEdit.EchoMode.Normal if self._key_visible else QLineEdit.EchoMode.Password)

    def _on_language_changed(self) -> None:
        language = str(self.language_combo.currentData())
        self.language_changed.emit(language)
        self.settings_changed.emit()

    def _show_export_menu(self) -> None:
        self._show_io_dialog(self._translator.t('export'), is_export=True)

    def _show_import_menu(self) -> None:
        self._show_io_dialog(self._translator.t('import'), is_export=False)

    _IO_GROUPS: list[tuple[str, list[str]]] = [
        ("io_group_settings", [
            CONFIG_SCOPE_APPEARANCE, CONFIG_SCOPE_MODEL_PARAMS,
            CONFIG_SCOPE_ENTRY_DEFAULTS, CONFIG_SCOPE_TAG_MARKERS,
        ]),
        ("io_group_content", [
            CONFIG_SCOPE_PROMPTS, CONFIG_SCOPE_EXAMPLES,
            CONFIG_SCOPE_OC_LIBRARY, CONFIG_SCOPE_ARTIST_LIBRARY,
            CONFIG_SCOPE_HISTORY,
        ]),
        ("io_group_window", [
            CONFIG_SCOPE_WINDOW_LAYOUT,
        ]),
    ]

    def _show_io_dialog(self, title: str, *, is_export: bool) -> None:
        from ..theme import current_palette, _fs

        pal = current_palette()

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setObjectName('PopupPanel')
        dlg.setFixedWidth(_dp(360))
        dlg.setStyleSheet(
            f"QDialog#PopupPanel {{ background: {pal['bg_surface']}; "
            f"border: 1px solid {pal['line_hover']}; border-radius: 10px; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(_dp(16), _dp(16), _dp(16), _dp(16))
        layout.setSpacing(_dp(8))

        title_label = QLabel(title, dlg)
        title_label.setStyleSheet(
            f"font-size: {_fs('fs_14')}; font-weight: bold; color: {pal['text']};"
        )
        layout.addWidget(title_label)

        sep = QFrame(dlg)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {pal['line']}; border: none;")
        layout.addWidget(sep)
        layout.addSpacing(_dp(6))

        scope_labels = self._config_scope_labels()
        config_boxes: list[tuple[str, QCheckBox]] = []

        for group_key, scopes in self._IO_GROUPS:
            card = QWidget(dlg)
            card.setStyleSheet(
                f"background: {pal['bg_input']}; "
                f"border: 1px solid {pal['line']}; border-radius: 6px;"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(8))
            card_layout.setSpacing(_dp(4))

            group_label = QLabel(self._translator.t(group_key), card)
            group_label.setStyleSheet(
                f"font-size: {_fs('fs_10')}; color: {pal['text_label']}; "
                f"font-weight: 500; border: none; padding: 0; margin: 0;"
            )
            card_layout.addWidget(group_label)

            for scope in scopes:
                cb = QCheckBox(scope_labels.get(scope, scope), card)
                cb.setChecked(True)
                cb.setStyleSheet("border: none;")
                card_layout.addWidget(cb)
                config_boxes.append((scope, cb))

            layout.addWidget(card)

        layout.addSpacing(_dp(8))

        tools_row = QHBoxLayout()
        tools_row.setContentsMargins(0, 0, 0, 0)
        tools_row.setSpacing(_dp(6))
        tools_row.addStretch()
        select_all_btn = QPushButton(self._translator.t('select_all'), dlg)
        select_all_btn.setObjectName('SecondaryButton')
        clear_btn = QPushButton(self._translator.t('select_none'), dlg)
        clear_btn.setObjectName('SecondaryButton')
        select_all_btn.clicked.connect(lambda _checked=False: [cb.setChecked(True) for _, cb in config_boxes])
        clear_btn.clicked.connect(lambda _checked=False: [cb.setChecked(False) for _, cb in config_boxes])
        tools_row.addWidget(select_all_btn)
        tools_row.addWidget(clear_btn)
        layout.addLayout(tools_row)

        layout.addSpacing(_dp(12))

        btn = QPushButton(title, dlg)
        btn.setObjectName('PrimaryButton')
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        checked_scopes = [scope for scope, cb in config_boxes if cb.isChecked()]
        if is_export:
            if checked_scopes:
                self.config_export_requested.emit(checked_scopes)
        else:
            if checked_scopes:
                self.config_import_requested.emit(checked_scopes)

    def _config_scope_labels(self) -> dict[str, str]:
        return {
            CONFIG_SCOPE_APPEARANCE: self._translator.t('config_scope_appearance'),
            CONFIG_SCOPE_MODEL_PARAMS: self._translator.t('config_scope_model_params'),
            CONFIG_SCOPE_PROMPTS: self._translator.t('config_scope_prompts'),
            CONFIG_SCOPE_EXAMPLES: self._translator.t('config_scope_examples'),
            CONFIG_SCOPE_OC_LIBRARY: self._translator.t('config_scope_oc_library'),
            CONFIG_SCOPE_ARTIST_LIBRARY: self._translator.t('config_scope_artist_library'),
            CONFIG_SCOPE_ENTRY_DEFAULTS: self._translator.t('config_scope_entry_defaults'),
            CONFIG_SCOPE_TAG_MARKERS: self._translator.t('config_scope_tag_markers'),
            CONFIG_SCOPE_WINDOW_LAYOUT: self._translator.t('config_scope_window_layout'),
            CONFIG_SCOPE_HISTORY: self._translator.t('config_scope_history'),
        }

    def target_width(self) -> int:
        return self._target_width

    def is_open(self) -> bool:
        return self._open

    def set_open(self, open_state: bool) -> None:
        self._open = open_state

    def toggle(self) -> bool:
        self._open = not self._open
        return self._open

    def open_panel(self) -> None:
        self._open = True

    def close_panel(self) -> None:
        self._open = False

    def set_request_fields_disabled(self, disabled: bool) -> None:
        for field in [self.api_base_url, self.api_key, self.model_combo]:
            field.setEnabled(not disabled)

    def set_ui_scale(self, percent: int) -> None:
        self._ui_scale_percent = percent
        self.settings_changed.emit()

    def set_font_size(self, pt: int) -> None:
        self._body_font_point_size = pt
        self.settings_changed.emit()

    def set_font_profile(self, profile: str, custom_id: str) -> None:
        self._font_profile = profile
        self._custom_font_id = custom_id
        self.settings_changed.emit()

    def settings(self) -> AppSettings:
        return AppSettings(
            api_base_url=self.api_base_url.text().strip(),
            api_key=self.api_key.text().strip(),
            model=self.model_combo.currentText().strip(),
            temperature=self.temperature_slider.value() * 0.1,
            top_p=self.top_p_slider.value() * 0.01,
            top_k=None if self.top_k_spin.value() < 0 else int(self.top_k_spin.value()),
            freq_penalty=self.freq_slider.value() * 0.1,
            pres_penalty=self.pres_slider.value() * 0.1,
            max_tokens=int(self.max_tokens_spin.value()),
            stream=self.stream_toggle.isChecked(),
            memory_mode=self.memory_toggle.isChecked(),
            send_mode=str(self.send_mode_combo.currentData() or SEND_MODE_ENTER),
            summary_prompt=self.summary_prompt_edit.toPlainText(),
            language=str(self.language_combo.currentData()),
            ui_scale_percent=self._ui_scale_percent,
            body_font_point_size=self._body_font_point_size,
            font_profile=self._font_profile,
            custom_font_id=self._custom_font_id,
            history_retention_days=int(self.history_retention_combo.currentData() or 30),
            default_example_order=self._def_example_order.value(),
            default_example_depth=self._def_example_depth.value(),
            default_oc_order=self._def_oc_order.value(),
            default_oc_depth=self._def_oc_depth.value(),
            tag_full_start=self._tag_full_start.text().strip(),
            tag_full_end=self._tag_full_end.text().strip(),
            tag_nochar_start=self._tag_nochar_start.text().strip(),
            tag_nochar_end=self._tag_nochar_end.text().strip(),
        )

    def apply_settings(self, settings: AppSettings) -> None:
        self.api_base_url.setText(settings.api_base_url)
        self.api_key.setText(settings.api_key)
        self.model_combo.setCurrentText(settings.model)
        self.temperature_slider.setValue(int(round(settings.temperature * 10)))
        self.top_p_slider.setValue(int(round(settings.top_p * 100)))
        self.top_k_spin.setValue(settings.top_k if settings.top_k is not None else -1)
        self.freq_slider.setValue(int(round(settings.freq_penalty * 10)))
        self.pres_slider.setValue(int(round(settings.pres_penalty * 10)))
        self.max_tokens_spin.setValue(settings.max_tokens)
        self.stream_toggle.setChecked(settings.stream)
        self.memory_toggle.setChecked(settings.memory_mode)
        send_mode_index = max(0, self.send_mode_combo.findData(settings.send_mode))
        self.send_mode_combo.setCurrentIndex(send_mode_index)
        self.summary_prompt_edit.setPlainText(settings.summary_prompt)
        language_index = max(0, self.language_combo.findData(settings.language))
        self.language_combo.setCurrentIndex(language_index)
        self._ui_scale_percent = settings.ui_scale_percent
        self._body_font_point_size = settings.body_font_point_size
        self._font_profile = settings.font_profile
        self._custom_font_id = settings.custom_font_id
        history_retention_index = max(0, self.history_retention_combo.findData(settings.history_retention_days))
        self.history_retention_combo.setCurrentIndex(history_retention_index)
        self._def_example_order.setValue(settings.default_example_order)
        self._def_example_depth.setValue(settings.default_example_depth)
        self._def_oc_order.setValue(settings.default_oc_order)
        self._def_oc_depth.setValue(settings.default_oc_depth)
        self._tag_full_start.setText(settings.tag_full_start)
        self._tag_full_end.setText(settings.tag_full_end)
        self._tag_nochar_start.setText(settings.tag_nochar_start)
        self._tag_nochar_end.setText(settings.tag_nochar_end)
        for slider in self._slider_meta:
            self._sync_slider_label(slider)

    def retranslate_ui(self) -> None:
        self.header_label.setText(self._translator.t('settings'))
        self.language_label.setText(self._translator.t('language'))

        current_language = self.language_combo.currentData()
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for language in self._translator.available_languages():
            self.language_combo.addItem(self._translator.t(f'language_{language}'), language)
        language_index = max(0, self.language_combo.findData(current_language or self._translator.get_language()))
        self.language_combo.setCurrentIndex(language_index)
        self.language_combo.blockSignals(False)

        current_send_mode = self.send_mode_combo.currentData()
        self.send_mode_label.setText(self._translator.t('send_mode'))
        self.send_mode_label.setToolTip(self._translator.t('tip_send_mode'))
        self.send_mode_combo.blockSignals(True)
        self.send_mode_combo.clear()
        self.send_mode_combo.addItem(self._translator.t('send_mode_enter'), SEND_MODE_ENTER)
        self.send_mode_combo.addItem(self._translator.t('send_mode_ctrl_enter'), SEND_MODE_CTRL_ENTER)
        send_mode_index = max(0, self.send_mode_combo.findData(current_send_mode or SEND_MODE_ENTER))
        self.send_mode_combo.setCurrentIndex(send_mode_index)
        self.send_mode_combo.blockSignals(False)

        self.api_label.setText(self._translator.t('api_base_url'))
        self.api_key_label.setText(self._translator.t('api_key'))
        self.eye_button.setToolTip(self._translator.t('show_hide'))
        self.model_label.setText(self._translator.t('model'))
        self.fetch_models_button.setToolTip(self._translator.t('fetch_models'))
        self.temperature_label.setText(self._translator.t('temperature'))
        self.temperature_label.setToolTip(self._translator.t('tip_temperature'))
        self.top_p_label.setText(self._translator.t('top_p'))
        self.top_p_label.setToolTip(self._translator.t('tip_top_p'))
        self.top_k_label.setText(self._translator.t('top_k'))
        self.top_k_label.setToolTip(self._translator.t('tip_top_k'))
        self.freq_label.setText(self._translator.t('freq_penalty'))
        self.freq_label.setToolTip(self._translator.t('tip_freq_penalty'))
        self.pres_label.setText(self._translator.t('pres_penalty'))
        self.pres_label.setToolTip(self._translator.t('tip_pres_penalty'))
        self.max_tokens_label.setText(self._translator.t('max_tokens'))
        self.max_tokens_label.setToolTip(self._translator.t('tip_max_tokens'))
        self.stream_label.setText(self._translator.t('stream'))
        self.stream_label.setToolTip(self._translator.t('tip_stream'))
        self.memory_label.setText(self._translator.t('memory_mode'))
        self.memory_label.setToolTip(self._translator.t('tip_memory'))
        current_history_retention = self.history_retention_combo.currentData()
        self.history_retention_label.setText(self._translator.t('history_retention'))
        self.history_retention_label.setToolTip(self._translator.t('tip_history_retention'))
        self.history_retention_combo.blockSignals(True)
        self.history_retention_combo.clear()
        for days in (0, 7, 30, 90):
            key = 'history_retention_never' if days == 0 else f'history_retention_{days}'
            self.history_retention_combo.addItem(self._translator.t(key), days)
        history_retention_index = max(0, self.history_retention_combo.findData(current_history_retention if current_history_retention is not None else 30))
        self.history_retention_combo.setCurrentIndex(history_retention_index)
        self.history_retention_combo.blockSignals(False)
        self.summary_prompt_label.setText(self._translator.t('summary_prompt'))
        self.summary_prompt_label.setToolTip(self._translator.t('tip_summary_prompt'))
        self.defaults_label.setText(self._translator.t('entry_defaults'))
        for key, label in getattr(self, "_default_field_labels", {}).items():
            label.setText(self._translator.t(key))
        self.markers_label.setText(self._translator.t('tag_markers'))
        self.markers_label.setToolTip(self._translator.t('tip_tag_markers'))
        self.export_button.setText(self._translator.t('export'))
        self.import_button.setText(self._translator.t('import'))
        self.check_update_button.setText(self._translator.t('check_update'))

        if not self.summary_prompt_edit.toPlainText().strip():
            self.summary_prompt_edit.setPlainText(self._translator.t('summary_default'))
        for slider in self._slider_meta:
            self._sync_slider_label(slider)
