from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QRect, QSize, Qt, QTimer, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QAction, QColor, QCursor, QGuiApplication, QIcon, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollBar,
    QSlider,
    QTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from functools import partial

from .api_client import ChatWorker
from .error_reporting import report_error, safe_context_from_settings
from .font_loader import build_body_font
from .theme import _fs
from .i18n import Translator
from .logic import build_messages, estimate_messages_tokens, normalize_api_base_url, validate_examples
from .models import (
    AppState,
    DockPosition,
    DockState,
    ExampleEntry,
    WidgetState,
    WindowState,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    CONFIG_FINE_SCOPES,
    CONFIG_SCOPE_APPEARANCE,
    CONFIG_SCOPE_ARTIST_LIBRARY,
    CONFIG_SCOPE_ENTRY_DEFAULTS,
    CONFIG_SCOPE_EXAMPLES,
    CONFIG_SCOPE_FULL_PROFILE,
    CONFIG_SCOPE_HISTORY,
    CONFIG_SCOPE_MODEL_PARAMS,
    CONFIG_SCOPE_OC_LIBRARY,
    CONFIG_SCOPE_PROMPTS,
    CONFIG_SCOPE_SETTINGS_PAGE,
    CONFIG_SCOPE_TAG_MARKERS,
    CONFIG_SCOPE_WINDOW_LAYOUT,
)
from .storage import AppStorage
from .ui_tokens import (
    BASE_WINDOW_HEIGHT,
    BASE_WINDOW_WIDTH,
    CLS_SUMMARY_TEXT,
    SAVE_DEBOUNCE_MS,
    SETTINGS_ANIM_DURATION,
    TITLEBAR_HEIGHT,
    WINDOW_EDGE_GAP,
    WINDOW_SURFACE_MARGIN,
    WINDOW_VISIBLE_RESIZE_BAND,
    WORKSPACE_PADDING,
    _dp,
)
from .widgets.dock import DockPanel
from .widgets.example_widget import ExampleWidget
from .widgets.input_widget import InputWidget
from .widgets.metadata_viewer import MetadataViewerWidget
from .widgets.metadata_destroyer import MetadataDestroyerWidget
from .widgets.image_manager import ImageManagerWindow
from .widgets.tag_completer import install_completer
from .tag_dictionary import TagDictionary
from .widgets.output_widget import OutputWidget
from .widgets.prompt_manager import PromptManagerWidget
from .widgets.settings_panel import SettingsPanel
from .widgets.widget_card import WidgetCard
from .widgets.workspace import DockQueryResult, Workspace

_CONVERSATION_HISTORY_MAX_MESSAGES = 20

if sys.platform == "win32":
    GWL_STYLE = -16
    WS_THICKFRAME = 0x00040000
    WS_MAXIMIZEBOX = 0x00010000
    WS_MINIMIZEBOX = 0x00020000
    WS_SYSMENU = 0x00080000
    WS_CAPTION = 0x00C00000
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_FRAMECHANGED = 0x0020
    SWP_NOACTIVATE = 0x0010
    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST = 0x0084
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17


class WindowSurface(QWidget):
    pass


class SummaryDialog(QDialog):
    def __init__(self, title: str, content: str, copy_label: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 360)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        editor = QTextEdit(self)
        editor.setProperty('class', CLS_SUMMARY_TEXT)
        editor.setReadOnly(True)
        editor.setPlainText(content)
        root.addWidget(editor, 1)

        button = QPushButton(copy_label, self)
        button.setObjectName('PrimaryButton')
        button.clicked.connect(lambda: QApplication.clipboard().setText(editor.toPlainText()))
        root.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)


class MainWindow(QWidget):
    def __init__(self, storage: AppStorage, translator: Translator) -> None:
        super().__init__()
        self._storage = storage
        self._translator = translator
        self._has_persisted_state = storage.settings_path.exists()
        self._state = storage.load_state()
        self._translator.set_language(self._state.settings.language)

        self._worker: ChatWorker | None = None
        self._current_mode = 'chat'
        self._startup_complete = False
        self._normal_geometry = QRect()
        self._title_drag_offset = QPoint()
        self._preview_position = ''
        self._next_example_index = 1
        self._example_cards: dict[str, tuple[WidgetCard, ExampleWidget]] = {}
        self._card_labels: dict[str, str] = {}
        self._settings_reveal = 0
        self._applying_shell_layout = False
        self._report_cooldowns: dict[str, float] = {}
        self._custom_palette: dict[str, str] | None = None
        if self._state.settings.theme == 'custom' and self._state.settings.custom_bg_image:
            from .theme import extract_palette_from_image
            self._custom_palette = extract_palette_from_image(self._state.settings.custom_bg_image)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._persist_state)

        self._settings_anim = QPropertyAnimation(self, b'settingsReveal', self)
        self._settings_anim.setDuration(SETTINGS_ANIM_DURATION)
        self._settings_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._settings_anim.finished.connect(self._finish_settings_animation)

        self.setObjectName('AppWindow')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(720, 480)
        self.setWindowTitle(self._translator.t('app_title'))
        icon_path = Path(__file__).parent / 'resources' / 'icon.png'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.surface = WindowSurface(self)
        self.surface.setObjectName('WindowSurface')
        self.surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.title_bar = QWidget(self.surface)
        self.title_bar.setObjectName('TitleBar')
        self.title_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)
        self.title_bar.installEventFilter(self)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(12, 6, 12, 6)
        title_layout.setSpacing(2)
        title_layout.addStretch(1)

        self.btn_settings = self._create_title_button('⚙', self._toggle_settings)
        self.btn_gallery = self._create_title_button('🖼', self._open_image_manager)
        self.btn_help = self._create_title_button('?', self._show_shortcuts_panel)
        self.btn_pin = self._create_title_button('📌', lambda: self._toggle_pin())
        self.btn_min = self._create_title_button('─', self.showMinimized)
        self.btn_max = self._create_title_button('□', self._toggle_maximize)
        self.btn_close = self._create_title_button('×', self.close, object_name='CloseButton')
        for button in [self.btn_settings, self.btn_gallery, self.btn_help, self.btn_pin, self.btn_min, self.btn_max, self.btn_close]:
            title_layout.addWidget(button)
        self._set_button_active(self.btn_settings, False)
        self._set_button_active(self.btn_pin, False)

        self.content_host = QWidget(self.surface)
        self.content_host.setObjectName('ContentHost')
        self.content_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.workspace = Workspace(self.content_host)
        self.workspace.setObjectName('Workspace')
        self.workspace.set_dock_query(self._dock_query)
        self.workspace.dock_requested.connect(self._dock_card)
        self.workspace.layout_changed.connect(self._schedule_save)

        # Version label — bottom-right corner of workspace
        from ._version import __version__
        self._version_label = QPushButton(f"v{__version__}", self.workspace)
        self._version_label.setObjectName('VersionLabel')
        self._version_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._version_label.setFlat(True)
        self._version_label.clicked.connect(self._show_changelog)
        self._version_label.setToolTip("Changelog")

        # Library panel (two-step scroll drawer from right)
        from .widgets.library_panel import LibraryPanel
        self._library_panel = LibraryPanel(self._translator, self._storage, self.workspace)
        self._library_panel.hide()
        self._library_panel.changed.connect(self._on_library_changed)
        self._library_panel.width_changed.connect(lambda _: self._position_library())
        self._library_open = False

        # Half-circle tab button on right edge (top-right area)
        self._lib_tab_btn = QPushButton("◂", self.workspace)
        self._lib_tab_btn.setObjectName("LibTabBtn")
        self._lib_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lib_tab_btn.setFixedSize(_dp(20), _dp(48))
        self._lib_tab_btn.clicked.connect(self._toggle_library)
        self._lib_tab_btn.setToolTip(self._translator.t("tip_library"))

        # Load library data
        artists, ocs = self._storage.load_library()
        if artists or ocs:
            self._library_panel.set_entries(artists, ocs)

        self.dock_preview = QWidget(self.content_host)
        self.dock_preview.setObjectName('DockPreview')
        self.dock_preview.hide()

        self._settings_backdrop = QWidget(self.content_host)
        self._settings_backdrop.setObjectName('SettingsBackdrop')
        self._settings_backdrop.hide()
        self._settings_backdrop.mousePressEvent = lambda e: self._set_settings_open(False)

        self.settings_panel = SettingsPanel(self._translator, self.content_host)
        self.settings_panel.hide()
        self.settings_panel.settings_changed.connect(self._on_settings_changed)
        self.settings_panel.language_changed.connect(self._change_language)
        self.settings_panel.export_prompts_requested.connect(self._export_prompts)
        self.settings_panel.import_prompts_requested.connect(self._import_prompts)
        self.settings_panel.config_export_requested.connect(self._export_config_bundle)
        self.settings_panel.config_import_requested.connect(self._import_config_bundle)
        self.settings_panel.fetch_models_requested.connect(self._fetch_models)
        self.settings_panel.check_update_button.clicked.connect(self.check_update_manual)

        self.dock_panel = DockPanel(self.content_host)
        self.dock_panel.set_container_rect_provider(self._usable_content_global_rect)
        self.dock_panel.state_changed.connect(self._on_dock_state_changed)
        self.dock_panel.preview_changed.connect(self._set_dock_preview)
        self.dock_panel.widget_activated.connect(lambda widget_id: self._restore_card(widget_id, None))
        self.dock_panel.widget_drag_restored.connect(self._restore_card)

        self.prompt_card = WidgetCard('widget-prompts', min_size=QSize(360, 260), parent=self.workspace)
        self.prompt_manager = PromptManagerWidget(self._translator, self.prompt_card)
        self.prompt_manager.changed.connect(self._on_prompts_changed)
        self.prompt_manager.preview_requested.connect(self._show_prompt_preview)
        self.prompt_card.set_content(self.prompt_manager)
        self.workspace.add_card(self.prompt_card)
        self._label_card(self.prompt_card, 'widget_prompts')

        self.main_card = WidgetCard('widget-main', min_size=QSize(520, 400), parent=self.workspace)
        main_container = QWidget(self.main_card)
        main_root = QVBoxLayout(main_container)
        main_root.setContentsMargins(0, 0, 0, 0)
        main_root.setSpacing(0)
        self._main_splitter = QSplitter(Qt.Orientation.Vertical, main_container)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setHandleWidth(6)
        self.output_widget = OutputWidget(self._translator, self._main_splitter)
        self.input_widget = InputWidget(self._translator, self._main_splitter)
        self._main_splitter.addWidget(self.output_widget)
        self._main_splitter.addWidget(self.input_widget)
        self._main_splitter.setStretchFactor(0, 3)
        self._main_splitter.setStretchFactor(1, 1)
        self.input_widget.setMinimumHeight(80)
        self.output_widget.setMinimumHeight(120)
        self._main_input_on_top = False
        main_root.addWidget(self._main_splitter, 1)
        self.main_card.set_content(main_container)
        # Swap button — floating on splitter handle
        self._swap_btn = QPushButton("⇅", main_container)
        self._swap_btn.setFixedSize(_dp(32), _dp(16))
        self._swap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swap_btn.setToolTip(self._translator.t('swap_layout'))
        self._swap_btn.setObjectName("SwapButton")
        self._swap_btn.clicked.connect(self._swap_main_sections)
        self._swap_btn.raise_()
        self._main_splitter.splitterMoved.connect(self._reposition_swap_btn)
        main_container.resizeEvent = lambda e: self._reposition_swap_btn()
        self.workspace.add_card(self.main_card)
        self._label_card(self.main_card, 'widget_main')

        # Metadata Viewer (single instance)
        self.metadata_viewer_card = WidgetCard('widget-metadata-viewer', min_size=QSize(380, 320), parent=self.workspace)
        self.metadata_viewer_widget = MetadataViewerWidget(self._translator, self.metadata_viewer_card)
        self.metadata_viewer_card.set_content(self.metadata_viewer_widget)
        self.workspace.add_card(self.metadata_viewer_card)
        self.metadata_viewer_card.hide()
        self._label_card(self.metadata_viewer_card, 'widget_metadata_viewer')

        # Metadata Destroyer (single instance)
        self.metadata_destroyer_card = WidgetCard('widget-metadata-destroyer', min_size=QSize(360, 280), parent=self.workspace)
        self.metadata_destroyer_widget = MetadataDestroyerWidget(self._translator, self.metadata_destroyer_card)
        self.metadata_destroyer_card.set_content(self.metadata_destroyer_widget)
        self.workspace.add_card(self.metadata_destroyer_card)
        self.metadata_destroyer_card.hide()
        self._label_card(self.metadata_destroyer_card, 'widget_metadata_destroyer')

        # Destroy template combo in title bar
        self._destroy_combo = QComboBox(self.metadata_destroyer_card._drag_strip)
        self._destroy_combo.setFixedHeight(_dp(22))
        self._destroy_combo.setMaximumWidth(100)
        self._destroy_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._destroy_combo.currentIndexChanged.connect(self._on_destroy_template_changed)
        self._destroy_combo.installEventFilter(self)
        self.metadata_destroyer_widget._edit_destroy_preset_requested.connect(
            lambda: QTimer.singleShot(100, lambda: self._show_destroy_template_menu(QCursor.pos()))
        )
        self._load_destroy_templates()

        # Position combo in destroyer card's resizeEvent
        _orig_destroyer_resize = self.metadata_destroyer_card.resizeEvent
        def _destroyer_resized(event):
            _orig_destroyer_resize(event)
            self._position_destroy_combo()
        self.metadata_destroyer_card.resizeEvent = _destroyer_resized

        # Image interrogator
        from .widgets.interrogator import InterrogatorWidget
        self.interrogator_card = WidgetCard('widget-interrogator', min_size=QSize(420, 500), parent=self.workspace)
        self.interrogator_widget = InterrogatorWidget(
            self._translator, self.interrogator_card,
            model_dir=self._state.settings.tagger_model_dir,
            python_path=self._state.settings.tagger_python_path,
        )
        self.interrogator_widget.send_to_input.connect(lambda text: self.input_widget.set_text(text))
        self.interrogator_widget.model_dir_changed.connect(self._on_tagger_model_dir_changed)
        self.interrogator_widget.python_path_changed.connect(self._on_tagger_python_path_changed)
        self.interrogator_card.set_content(self.interrogator_widget)
        self.workspace.add_card(self.interrogator_card)
        self.interrogator_card.hide()
        self._label_card(self.interrogator_card, 'interrogator')

        # History sidebar (right of main_card)
        from .widgets.history_sidebar import HistorySidebar
        self._history_sidebar = HistorySidebar(self._translator, self._storage, self.workspace)
        self._history_sidebar.hide()
        self._history_sidebar.entry_fill_requested.connect(self._on_history_fill)
        self._history_sidebar.width_changed.connect(lambda _: self._position_history_sidebar())
        self._history_open = False

        # History toggle button — workspace child, positioned at main_card's right edge
        self._history_tab_btn = QPushButton("◁", self.workspace)
        self._history_tab_btn.setObjectName("HistTabBtn")
        self._history_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_tab_btn.setFixedSize(_dp(16), _dp(80))
        self._history_tab_btn.clicked.connect(self._toggle_history_sidebar)
        self._history_tab_btn.setToolTip(self._translator.t("history_panel"))

        # Follow main_card on every move/resize (fires during drag, not just on release)
        self.main_card.geometry_live.connect(self._position_history_btn)
        self.main_card.geometry_live.connect(self._position_history_sidebar)


        # Load existing history
        entries = self._storage.load_history()
        if entries:
            self._history_sidebar.set_entries(entries)

        # Track main_card float/unfloat — reparent history button
        self.main_card.floated.connect(lambda _: self._reparent_history_btn_to_card())
        self.main_card.unfloated.connect(lambda _: self._reparent_history_btn_to_workspace())

        # Workspace drag-and-drop → open metadata viewer
        self.workspace.image_dropped.connect(self._on_workspace_image_dropped)

        self._conversation_history: list[dict[str, str]] = []
        self._pending_history_input: str = ""
        self._pending_history_model: str = ""

        self._tag_dictionary = TagDictionary()
        csv_name = 'danbooru_all_2.csv'
        # Check dist/_internal first, then project root
        for base in [Path(sys.executable).parent, Path(__file__).resolve().parent.parent]:
            csv_path = base / csv_name
            if csv_path.exists():
                self._tag_dictionary.load_csv(csv_path)
                break
        self.output_widget.set_dictionary(self._tag_dictionary)

        # Install tag autocomplete on input editor and output editors
        install_completer(self.input_widget.editor, self._tag_dictionary)
        install_completer(self.output_widget.full_editor, self._tag_dictionary)
        install_completer(self.output_widget.nochar_editor, self._tag_dictionary)

        self.input_widget.send_button.clicked.connect(self._handle_send_action)
        self.input_widget.summary_button.clicked.connect(self._handle_summary_action)
        self.input_widget.editor.textChanged.connect(self._on_editor_changed)

        # Hint manager (feature discoverability framework)
        from .widgets.hint_manager import HintManager
        self._hint_manager = HintManager(self._storage, self._translator)

        self._setup_shortcuts()
        self._setup_context_menus()
        self._load_state_into_ui()
        self._restore_window_geometry()
        QTimer.singleShot(0, self._finish_startup)

    @pyqtProperty(int)
    def settingsReveal(self) -> int:
        return self._settings_reveal

    @settingsReveal.setter
    def settingsReveal(self, value: int) -> None:
        self._settings_reveal = max(0, min(int(value), self.settings_panel.target_width()))
        self._position_settings_overlay()

    def _create_title_button(self, text: str, slot, *, object_name: str = 'TitleBarButton') -> QPushButton:
        button = QPushButton(text, self.title_bar)
        button.setObjectName(object_name)
        button.clicked.connect(slot)
        return button

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence('Ctrl+Enter'), self, activated=self._handle_send_action)
        QShortcut(QKeySequence('Ctrl+Return'), self, activated=self._handle_send_action)
        QShortcut(QKeySequence('Ctrl+Shift+S'), self, activated=self._handle_summary_action)
        QShortcut(QKeySequence('Esc'), self, activated=self._handle_escape)
        QShortcut(QKeySequence('F1'), self, activated=self._show_shortcuts_panel)
        QShortcut(QKeySequence('Ctrl+/'), self, activated=self._show_shortcuts_panel)

    def _setup_context_menus(self) -> None:
        self.workspace.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.workspace.customContextMenuRequested.connect(self._show_workspace_menu)

        self.dock_panel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dock_panel.customContextMenuRequested.connect(self._show_dock_menu)
        self.dock_panel.widget_close_requested.connect(self._close_dock_item)

        self.input_widget.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.input_widget.editor.customContextMenuRequested.connect(self._show_input_menu)

    def _set_button_active(self, button: QPushButton, active: bool) -> None:
        button.setProperty('active', active)
        self.style().unpolish(button)
        self.style().polish(button)

    def _load_state_into_ui(self) -> None:
        self.settings_panel.apply_settings(self._state.settings)
        self.prompt_manager.set_prompt_entries(self._state.prompts)
        self.input_widget.set_text(self._state.input_history)
        self.dock_panel.set_state(self._state.dock)

        saved_widget_states = {item.widget_id: item for item in self._state.widgets}
        prompt_state = saved_widget_states.get('widget-prompts')
        main_state = saved_widget_states.get('widget-main') or saved_widget_states.get('widget-input')

        if not self._has_persisted_state:
            self.prompt_card.hide()
            self.main_card.show()
            # Create default example cards (docked)
            for index, example in enumerate(self._state.examples, start=1):
                self._next_example_index = index + 1
                docked_state = WidgetState(widget_id=f'widget-example-{index}', visible=False, docked=True)
                self._create_example_card(example, widget_id=f'widget-example-{index}', state=docked_state)
            self._refresh_dock_items()
            return

        if prompt_state is not None:
            if prompt_state.width > 0 and prompt_state.height > 0:
                self.prompt_card.setGeometry(prompt_state.x, prompt_state.y, prompt_state.width, prompt_state.height)
            if prompt_state.visible and not prompt_state.docked:
                self.prompt_card.show()
            else:
                self.prompt_card.hide()
        else:
            self.prompt_card.hide()

        if main_state is not None:
            self.main_card.setGeometry(main_state.x, main_state.y, main_state.width, main_state.height)
            if main_state.visible and not main_state.docked:
                self.main_card.show()
            else:
                self.main_card.hide()
        else:
            self.main_card.show()

        for index, example in enumerate(self._state.examples, start=1):
            widget_id = f'widget-example-{index}'
            self._next_example_index = index + 1
            state = saved_widget_states.get(widget_id)
            self._create_example_card(example, widget_id=widget_id, state=state)

    def _clear_example_cards(self, *, remove_assets: bool) -> None:
        for widget_id, (_card, editor) in list(self._example_cards.items()):
            if remove_assets:
                editor.remove_assets()
            self.workspace.remove_card(widget_id)
            self._example_cards.pop(widget_id, None)
            self._card_labels.pop(widget_id, None)
        self._next_example_index = 1

    def _restore_available_geometry(self, saved: WindowState | None = None) -> QRect:
        screens = QGuiApplication.screens()
        if not screens:
            return QRect(0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        if saved is not None and self._has_persisted_state:
            if saved.screen_device_name:
                for screen in screens:
                    if screen.name() == saved.screen_device_name:
                        return screen.availableGeometry()
            saved_center = QPoint(saved.x + max(1, saved.width) // 2, saved.y + max(1, saved.height) // 2)
            for screen in screens:
                if screen.availableGeometry().contains(saved_center):
                    return screen.availableGeometry()
        screen = QGuiApplication.primaryScreen() or (screens[0] if screens else None)
        if screen is None:
            return QRect(0, 0, 1280, 800)
        return screen.availableGeometry()

    def _fit_base_rect_to_available(self, rect: QRect, available: QRect) -> QRect:
        min_width = min(720, max(320, available.width()))
        min_height = min(480, max(240, available.height()))
        fitted = QRect(rect)
        fitted.setWidth(min(available.width(), max(min_width, rect.width())))
        fitted.setHeight(min(available.height(), max(min_height, rect.height())))
        if fitted.right() > available.right():
            fitted.moveRight(available.right())
        if fitted.bottom() > available.bottom():
            fitted.moveBottom(available.bottom())
        if fitted.left() < available.left():
            fitted.moveLeft(available.left())
        if fitted.top() < available.top():
            fitted.moveTop(available.top())
        if not available.contains(fitted.center()):
            fitted.moveCenter(available.center())
        return fitted

    def _restore_window_geometry(self) -> None:
        saved = self._state.window
        screen = self._restore_available_geometry(saved)
        first_width = min(BASE_WINDOW_WIDTH, int(round(screen.width() * 0.92)))
        first_height = min(BASE_WINDOW_HEIGHT, int(round(screen.height() * 0.92)))

        if not self._has_persisted_state:
            target = QRect(
                screen.x() + (screen.width() - first_width) // 2,
                screen.y() + (screen.height() - first_height) // 2,
                first_width,
                first_height,
            )
            self._normal_geometry = target
            self.setGeometry(self._fit_base_rect_to_available(target, screen))
            return

        scale_x = screen.width() / max(1, saved.available_screen_width)
        scale_y = screen.height() / max(1, saved.available_screen_height)
        target = QRect(
            screen.x() + int(round((saved.x - saved.available_screen_x) * scale_x)),
            screen.y() + int(round((saved.y - saved.available_screen_y) * scale_y)),
            int(round(saved.width * scale_x)),
            int(round(saved.height * scale_y)),
        )
        if saved.width == 1200 and saved.height == 760:
            target.setWidth(max(target.width(), first_width))
            target.setHeight(max(target.height(), first_height))
        target = self._fit_base_rect_to_available(target, screen)
        self._normal_geometry = target
        self.setGeometry(self._fit_base_rect_to_available(target, screen))
        if saved.pinned:
            self._toggle_pin(force=True)

    def _finish_startup(self) -> None:
        self._startup_complete = True
        self._retranslate_ui()
        self._apply_shell_layout()
        self._apply_background_image()
        self._restore_widget_layouts()
        self._refresh_dock_items()
        self._update_token_estimate()
        if self._state.window.maximized:
            self.showMaximized()
            self._apply_native_window_style()
        QTimer.singleShot(100, self._reposition_swap_btn)
        QTimer.singleShot(100, self._position_history_btn)
        if not self._has_persisted_state:
            QTimer.singleShot(800, self._start_onboarding)
        else:
            self._register_hints()
        # Auto update check (delayed 3s to not block startup)
        QTimer.singleShot(3000, self._check_update_auto)

    def _restore_widget_layouts(self) -> None:
        saved_widget_states = {item.widget_id: item for item in self._state.widgets}
        current_screen = self._current_available_geometry()
        saved_window = self._state.window
        scale_x = current_screen.width() / max(1, saved_window.available_screen_width or current_screen.width())
        scale_y = current_screen.height() / max(1, saved_window.available_screen_height or current_screen.height())
        input_state = saved_widget_states.get('widget-input')

        if not self._has_persisted_state or not saved_widget_states or input_state is None:
            self.prompt_card.hide()
            self._apply_default_input_layout()
            self._layout_visible_examples_default()
            return

        self.workspace.apply_widget_states(self._state.widgets)
        if abs(scale_x - 1.0) > 0.001 or abs(scale_y - 1.0) > 0.001:
            self.workspace.scale_layout(scale_x, scale_y)
            dock_state = self.dock_panel.state()
            if dock_state.position == DockPosition.FLOATING:
                dock_state.floating_x = int(round(dock_state.floating_x * scale_x))
                dock_state.floating_y = int(round(dock_state.floating_y * scale_y))
                dock_state.floating_width = int(round(dock_state.floating_width * scale_x))
                dock_state.floating_height = int(round(dock_state.floating_height * scale_y))
                self.dock_panel.set_state(dock_state)
        for card in self.workspace.visible_cards():
            self.workspace.clamp_card(card)
        if input_state.width <= 0 or input_state.height <= 0:
            self._apply_default_input_layout()
        elif self.main_card.isVisible():
            self.workspace.resolve_overlap(self.main_card)

    def _reposition_swap_btn(self, *_args) -> None:
        handle = self._main_splitter.handle(1)
        if handle is None:
            return
        # Map handle center to main_container coordinates
        container = self._swap_btn.parentWidget()
        handle_pos = handle.mapTo(container, QPoint(handle.width() // 2, handle.height() // 2))
        self._swap_btn.move(
            handle_pos.x() - self._swap_btn.width() // 2,
            handle_pos.y() - self._swap_btn.height() // 2,
        )
        self._swap_btn.raise_()

    def _swap_main_sections(self) -> None:
        sizes = self._main_splitter.sizes()
        self._main_input_on_top = not self._main_input_on_top
        # Remove and re-add in swapped order
        self.output_widget.setParent(None)
        self.input_widget.setParent(None)
        if self._main_input_on_top:
            self._main_splitter.addWidget(self.input_widget)
            self._main_splitter.addWidget(self.output_widget)
        else:
            self._main_splitter.addWidget(self.output_widget)
            self._main_splitter.addWidget(self.input_widget)
        self._main_splitter.setSizes(list(reversed(sizes)))
        self._schedule_save()

    def _apply_default_input_layout(self) -> None:
        workspace_rect = self.workspace.rect()
        if workspace_rect.width() <= 0 or workspace_rect.height() <= 0:
            return
        max_width = max(320, workspace_rect.width() - 24)
        max_height = max(220, workspace_rect.height() - 24)
        width = min(max_width, max(520, int(round(workspace_rect.width() * 0.62))))
        height = min(max_height, max(340, int(round(workspace_rect.height() * 0.70))))
        x = max(12, int(round((workspace_rect.width() - width) / 2 + workspace_rect.width() * 0.06)))
        y = max(12, int(round((workspace_rect.height() - height) / 2)))
        if x + width > workspace_rect.width() - 12:
            x = max(12, workspace_rect.width() - width - 12)
        if y + height > workspace_rect.height() - 12:
            y = max(12, workspace_rect.height() - height - 12)
        self.main_card.setGeometry(x, y, width, height)
        self.main_card.show()
        self.workspace.resolve_overlap(self.main_card)

    def _layout_visible_examples_default(self) -> None:
        for card, _editor in self._example_cards.values():
            if not card.isVisible():
                continue
            card.setGeometry(self.workspace.find_free_position(QSize(360, 320), exclude=card))
            self.workspace.resolve_overlap(card)

    def _label_card(self, card: WidgetCard, i18n_key: str) -> None:
        label = self._translator.t(i18n_key)
        self._card_labels[card.widget_id] = label
        card.set_title(label)

    def _create_example_card(
        self,
        entry: ExampleEntry | None = None,
        *,
        widget_id: str | None = None,
        state: WidgetState | None = None,
    ) -> None:
        widget_id = widget_id or f'widget-example-{self._next_example_index}'
        self._next_example_index += 1
        card = WidgetCard(widget_id, min_size=QSize(340, 280), parent=self.workspace)
        if entry is None:
            s = self._state.settings
            entry = ExampleEntry(order=s.default_example_order, depth=s.default_example_depth)
        editor = ExampleWidget(self._translator, self._storage, entry, card)
        editor.changed.connect(self._on_examples_changed)
        editor.delete_requested.connect(self._delete_example_card)
        editor.error_occurred.connect(self._on_example_storage_error)
        install_completer(editor.tags_edit, self._tag_dictionary)
        card.set_content(editor)
        self.workspace.add_card(card)
        card.retranslate_ui(self._translator.t('grip_title'), self._translator.t('resize_title'), self._translator.t('tip_close_card'))
        if state is not None:
            card.setGeometry(state.x, state.y, state.width, state.height)
            if not state.visible or state.docked:
                card.hide()
        else:
            card.setGeometry(self.workspace.find_free_position(QSize(360, 320), exclude=card))
        label = f"{self._translator.t('example')} {len(self._example_cards) + 1}"
        self._card_labels[widget_id] = label
        card.set_title(label)
        self._example_cards[widget_id] = (card, editor)
        self._refresh_dock_items()
        self._schedule_save()

    def _close_dock_item(self, widget_id: str) -> None:
        if widget_id.startswith('widget-example-'):
            card_entry = self._example_cards.get(widget_id)
            if card_entry is not None:
                _card, editor = card_entry
                self._delete_example_card(editor)

    def _delete_example_card(self, widget: ExampleWidget) -> None:
        for widget_id, (card, editor) in list(self._example_cards.items()):
            if editor is widget:
                editor.remove_assets()
                self.workspace.remove_card(widget_id)
                card.setParent(None)
                card.deleteLater()
                del self._example_cards[widget_id]
                self._card_labels.pop(widget_id, None)
                self._refresh_dock_items()
                self._schedule_save()
                self._update_token_estimate()
                return

    def _dock_query(self) -> DockQueryResult | None:
        if not self.dock_panel.isVisible():
            return None
        return DockQueryResult(self.dock_panel.dock_capture_rect(), self.dock_panel.state().position)

    def _dock_card(self, widget_id: str) -> None:
        self.workspace.hide_card(widget_id)
        if widget_id == 'widget-main':
            self._on_main_card_visibility_changed()
        self._refresh_dock_items()
        self._schedule_save()

    def _restore_card(self, widget_id: str, global_pos: QPoint | None) -> None:
        card = self.workspace.card(widget_id)
        if card is None:
            return
        card.show()
        self.workspace.restore_card(card, drop_point=global_pos)
        if widget_id == 'widget-main':
            self._on_main_card_visibility_changed()
        self._refresh_dock_items()
        self._schedule_save()

    def _restore_prompts_card(self) -> None:
        if self.prompt_card.isVisible():
            self.prompt_card.raise_()
            return
        self._restore_card(self.prompt_card.widget_id, None)

    def _dock_prompts_card(self) -> None:
        self._dock_card(self.prompt_card.widget_id)

    def _reset_layout(self) -> None:
        if self.settings_panel.is_open():
            self._set_settings_open(False)
        dock_state = DockState()
        self.dock_panel.set_state(dock_state)
        self.prompt_card.hide()
        self._apply_default_input_layout()
        for card, _editor in self._example_cards.values():
            card.show()
            card.setGeometry(self.workspace.find_free_position(QSize(360, 320), exclude=card))
            self.workspace.resolve_overlap(card)
        self._refresh_dock_items()
        self._schedule_save()

    def _clear_input_history(self) -> None:
        self.input_widget.clear_text()
        self._update_token_estimate()
        self._schedule_save()

    def _clear_conversation_history(self) -> None:
        self._conversation_history.clear()
        self._update_token_estimate()

    def _trim_conversation_history(self) -> None:
        if len(self._conversation_history) > _CONVERSATION_HISTORY_MAX_MESSAGES:
            del self._conversation_history[:-_CONVERSATION_HISTORY_MAX_MESSAGES]

    def _refresh_dock_items(self) -> None:
        items: list[tuple[str, str, str]] = []
        icons = {'widget-prompts': 'P', 'widget-input': 'I'}
        for card in self.workspace.all_cards():
            if card.isVisible():
                continue
            label = self._card_labels.get(card.widget_id, card.widget_id)
            icon = icons.get(card.widget_id, 'E' if card.widget_id.startswith('widget-example-') else 'W')
            items.append((card.widget_id, icon, label))
        self.dock_panel.set_items(items)

    def _collect_examples(self) -> list[ExampleEntry]:
        return [editor.entry() for _, editor in self._example_cards.values()]

    def _collect_widget_states(self) -> list[WidgetState]:
        states = self.workspace.widget_states()
        states.sort(key=lambda item: item.widget_id)
        return states

    def _base_window_geometry(self) -> QRect:
        if self._normal_geometry.isValid() and not self.isMaximized():
            return QRect(self._normal_geometry)
        return QRect(self.geometry())

    def _build_app_state(self) -> AppState:
        settings = self.settings_panel.settings()
        settings.language = self._translator.get_language()
        # Preserve state-only fields not managed by settings panel
        settings.theme = self._state.settings.theme
        settings.card_opacity = self._state.settings.card_opacity
        settings.custom_bg_image = self._state.settings.custom_bg_image
        settings.bg_blur = self._state.settings.bg_blur
        settings.bg_opacity = self._state.settings.bg_opacity
        settings.bg_brightness = self._state.settings.bg_brightness
        settings.workspace_menu_order = self._state.settings.workspace_menu_order
        settings.image_manager_folder = self._state.settings.image_manager_folder
        settings.skipped_version = self._state.settings.skipped_version
        settings.destroy_templates = self._state.settings.destroy_templates
        settings.active_destroy_template = self._state.settings.active_destroy_template
        settings.tagger_model_dir = self._state.settings.tagger_model_dir
        settings.tagger_python_path = self._state.settings.tagger_python_path
        window_geometry = self._base_window_geometry()
        available = self._current_available_geometry()
        self._state.settings = settings
        self._state.window = self._state.window.__class__(
            x=window_geometry.x(),
            y=window_geometry.y(),
            width=window_geometry.width(),
            height=window_geometry.height(),
            maximized=self.isMaximized(),
            pinned=bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint),
            available_screen_x=available.x(),
            available_screen_y=available.y(),
            available_screen_width=available.width(),
            available_screen_height=available.height(),
            screen_device_name=self._current_screen_name(),
        )
        self._state.dock = self.dock_panel.state()
        self._state.prompts = self.prompt_manager.prompt_entries()
        self._state.examples = self._collect_examples()
        self._state.widgets = self._collect_widget_states()
        self._state.input_history = self.input_widget.text()
        return self._state

    def _persist_state(self) -> None:
        try:
            self._storage.save_state(self._build_app_state())
        except Exception as exc:
            self._report_issue(
                'storage_error',
                self._translator.t('error_save_state_failed'),
                action='save_state',
                details=self._traceback_details(exc),
                dedupe_key='save_state',
                dedupe_seconds=12.0,
            )

    def _config_filename_for_scope(self, scopes: str | list[str]) -> str:
        normalized = self._normalize_config_scopes(scopes)
        if normalized == CONFIG_FINE_SCOPES:
            return 'full-profile.aitg.json'
        if len(normalized) == 1:
            return f'{normalized[0]}.aitg.json'
        if scopes == CONFIG_SCOPE_FULL_PROFILE:
            return 'full-profile.aitg.json'
        if scopes == CONFIG_SCOPE_SETTINGS_PAGE:
            return 'settings-page.aitg.json'
        return 'selected-config.aitg.json'

    def _normalize_config_scopes(self, scopes: str | list[str]) -> list[str]:
        if scopes == CONFIG_SCOPE_FULL_PROFILE:
            return list(CONFIG_FINE_SCOPES)
        if scopes == CONFIG_SCOPE_SETTINGS_PAGE:
            return [
                CONFIG_SCOPE_APPEARANCE,
                CONFIG_SCOPE_MODEL_PARAMS,
                CONFIG_SCOPE_ENTRY_DEFAULTS,
                CONFIG_SCOPE_TAG_MARKERS,
                CONFIG_SCOPE_WINDOW_LAYOUT,
            ]
        raw_scopes = scopes if isinstance(scopes, list) else [scopes]
        return [scope for scope in CONFIG_FINE_SCOPES if scope in raw_scopes]

    def _apply_pinned_state(self, pinned: bool) -> None:
        current = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if current != pinned:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
            self.show()
        self._apply_native_window_style()
        self._set_button_active(self.btn_pin, pinned)

    def _apply_full_profile_state(self, state: AppState) -> None:
        previous_startup = self._startup_complete
        retained_example_paths = {entry.image_path for entry in state.examples if entry.image_path}
        obsolete_example_paths = {
            entry.image_path
            for entry in self._collect_examples()
            if entry.image_path and entry.image_path not in retained_example_paths
        }
        self._startup_complete = False
        self._settings_anim.stop()
        self.settings_panel.set_open(False)
        self._settings_reveal = 0
        self.settings_panel.hide()
        self._settings_backdrop.hide()
        self._set_button_active(self.btn_settings, False)
        if self.isMaximized():
            self.showNormal()
        self._has_persisted_state = True
        self._state = state
        self._clear_example_cards(remove_assets=False)
        for image_path in obsolete_example_paths:
            self._storage.remove_example_image(image_path)
        self._load_state_into_ui()
        self._restore_window_geometry()
        self._apply_pinned_state(state.window.pinned)
        self._apply_shell_layout()
        self._restore_widget_layouts()
        if state.window.maximized:
            self.showMaximized()
            self._apply_native_window_style()
        self._retranslate_ui()
        self._update_token_estimate()
        self._startup_complete = previous_startup or True
        self._schedule_save()

    def _schedule_save(self) -> None:
        if not self._startup_complete:
            return
        self._save_timer.start()

    def _on_settings_changed(self) -> None:
        s = self.settings_panel.settings()
        self._library_panel.set_oc_defaults(s.default_oc_order, s.default_oc_depth)
        self._update_token_estimate()
        self._schedule_save()

    def _on_prompts_changed(self) -> None:
        self._update_token_estimate()
        self._schedule_save()

    def _on_examples_changed(self) -> None:
        self._update_token_estimate()
        self._schedule_save()

    def _on_example_storage_error(self, message: str, details: str) -> None:
        self._report_issue(
            'storage_error',
            message,
            action='example_image',
            details=details,
            extra_context={'widget': 'example'},
        )

    def _on_editor_changed(self) -> None:
        self._update_token_estimate()
        self._schedule_save()

    def _on_dock_state_changed(self) -> None:
        self._apply_content_layout()
        self._schedule_save()

    def _set_dock_preview(self, position: str) -> None:
        self._preview_position = position
        self._apply_content_layout()

    def _set_settings_open(self, open_state: bool) -> None:
        self._settings_anim.stop()
        self.settings_panel.set_open(open_state)
        self._set_button_active(self.btn_settings, open_state)
        if open_state:
            self._settings_backdrop.show()
            self.settings_panel.show()
            self._settings_backdrop.raise_()
            self.settings_panel.raise_()
        target = self.settings_panel.target_width() if open_state else 0
        self._settings_anim.setStartValue(self._settings_reveal)
        self._settings_anim.setEndValue(target)
        self._settings_anim.start()

    def _finish_settings_animation(self) -> None:
        if self._settings_reveal == 0:
            self.settings_panel.hide()
            self._settings_backdrop.hide()

    def _position_settings_overlay(self) -> None:
        ch = self.content_host
        self._settings_backdrop.setGeometry(0, 0, ch.width(), ch.height())
        self.settings_panel.setGeometry(
            ch.width() - self._settings_reveal, 0,
            self.settings_panel.target_width(), ch.height(),
        )

    def _toggle_settings(self) -> None:
        self._set_settings_open(not self.settings_panel.is_open())

    def _handle_escape(self) -> None:
        if self.settings_panel.is_open():
            self._set_settings_open(False)

    def _toggle_pin(self, force: bool | None = None) -> None:
        currently_pinned = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        target = (not currently_pinned) if force is None else force
        self._apply_pinned_state(target)
        self._schedule_save()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.setGeometry(self._base_window_geometry())
        else:
            self._normal_geometry = QRect(self.geometry())
            self.showMaximized()
        self._apply_native_window_style()
        self._schedule_save()

    def _apply_native_window_style(self) -> None:
        if sys.platform != 'win32':
            return
        try:
            hwnd = int(self.winId())
        except (TypeError, ValueError):
            return
        if hwnd == 0:
            return
        user32 = ctypes.windll.user32
        style = int(user32.GetWindowLongW(hwnd, GWL_STYLE))
        target_style = style | WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU
        target_style &= ~WS_CAPTION
        if target_style == style:
            return
        user32.SetWindowLongW(hwnd, GWL_STYLE, target_style)
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE,
        )

    def _current_available_geometry(self) -> QRect:
        handle = self.windowHandle()
        if handle is not None and handle.screen() is not None:
            return handle.screen().availableGeometry()
        center = self.geometry().center() if self.geometry().isValid() else QPoint(100, 100)
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else QRect(0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

    def _current_screen_name(self) -> str:
        handle = self.windowHandle()
        if handle is not None and handle.screen() is not None:
            return handle.screen().name()
        center = self.geometry().center() if self.geometry().isValid() else QPoint(100, 100)
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        return screen.name() if screen is not None else ''

    def _apply_shell_layout(self) -> None:
        if self._applying_shell_layout:
            return
        self._applying_shell_layout = True
        try:
            outer = self.rect().adjusted(WINDOW_SURFACE_MARGIN, WINDOW_SURFACE_MARGIN, -WINDOW_SURFACE_MARGIN, -WINDOW_SURFACE_MARGIN)
            self.surface.setGeometry(outer)
            self.title_bar.setGeometry(0, 0, outer.width(), TITLEBAR_HEIGHT)
            self.content_host.setGeometry(0, TITLEBAR_HEIGHT, outer.width(), outer.height() - TITLEBAR_HEIGHT)
            self._apply_content_layout()
            if self._settings_reveal > 0 or self.settings_panel.is_open():
                self._position_settings_overlay()
        finally:
            self._applying_shell_layout = False

    def _usable_content_global_rect(self) -> QRect:
        local = self._usable_content_local_rect()
        return QRect(self.content_host.mapToGlobal(local.topLeft()), local.size())

    def _usable_content_local_rect(self) -> QRect:
        return QRect(0, 0, self.content_host.width(), self.content_host.height())

    def _apply_content_layout(self) -> None:
        content_rect = self._usable_content_local_rect()
        dock_rect = self.dock_panel.desired_rect(content_rect)
        if self.dock_panel.state().position == DockPosition.LEFT:
            workspace_rect = QRect(content_rect)
            workspace_rect.setLeft(dock_rect.right() + 1)
        elif self.dock_panel.state().position == DockPosition.RIGHT:
            workspace_rect = QRect(content_rect)
            workspace_rect.setRight(dock_rect.left() - 1)
        elif self.dock_panel.state().position == DockPosition.TOP:
            workspace_rect = QRect(content_rect)
            workspace_rect.setTop(dock_rect.bottom() + 1)
        elif self.dock_panel.state().position == DockPosition.BOTTOM:
            workspace_rect = QRect(content_rect)
            workspace_rect.setBottom(dock_rect.top() - 1)
        else:
            workspace_rect = QRect(content_rect)
        self.workspace.setGeometry(workspace_rect)
        # Position version label at bottom-right of workspace
        vl = self._version_label
        vl.adjustSize()
        vl.move(workspace_rect.width() - vl.width() - 8,
                workspace_rect.height() - vl.height() - 4)
        vl.raise_()
        # Position library tab button and panel
        self._position_library()
        self._position_history_sidebar()
        self.dock_panel.setGeometry(dock_rect)
        self.dock_panel.raise_()
        self._update_dock_preview_geometry(content_rect)

    def _update_dock_preview_geometry(self, content_rect: QRect) -> None:
        if self._preview_position not in {DockPosition.LEFT, DockPosition.RIGHT, DockPosition.TOP, DockPosition.BOTTOM}:
            self.dock_preview.hide()
            return
        if self._preview_position == DockPosition.LEFT:
            rect = QRect(content_rect.x(), content_rect.y(), 36, content_rect.height())
        elif self._preview_position == DockPosition.RIGHT:
            rect = QRect(content_rect.right() - 35, content_rect.y(), 36, content_rect.height())
        elif self._preview_position == DockPosition.TOP:
            rect = QRect(content_rect.x(), content_rect.y(), content_rect.width(), 36)
        else:
            rect = QRect(content_rect.x(), content_rect.bottom() - 35, content_rect.width(), 36)
        self.dock_preview.setGeometry(rect)
        self.dock_preview.show()
        self.dock_preview.raise_()

    # Basic items shown by default; other items available in customize panel
    _DEFAULT_MENU_ORDER = ['tidy', 'prompts', 'add_example', 'appearance', '---', 'settings', 'pin']
    _ALL_MENU_ITEMS = ['tidy', 'prompts', 'add_example', 'metadata_viewer', 'metadata_destroyer', 'interrogator', 'history', 'image_manager', 'shortcuts', 'clear', 'reset', 'appearance', '---', 'settings', 'pin']

    def _workspace_menu_items(self) -> dict[str, tuple[str, callable]]:
        t = self._translator.t
        return {
            'tidy': (t('tidy_workspace'), self._tidy_workspace),
            'prompts': (t('dock_prompts') if self.prompt_card.isVisible() else t('restore_prompts'),
                        self._dock_prompts_card if self.prompt_card.isVisible() else self._restore_prompts_card),
            'add_example': (t('add_example'), self._add_example_card),
            'metadata_viewer': (t('metadata_viewer'), self._toggle_metadata_viewer),
            'metadata_destroyer': (t('metadata_destroyer'), self._toggle_metadata_destroyer),
            'interrogator': (t('interrogator'), self._toggle_interrogator),
            'history': (t('history_panel'), self._toggle_history_sidebar),
            'image_manager': (t('image_manager'), self._open_image_manager),
            'shortcuts': (t('shortcuts'), self._show_shortcuts_panel),
            'clear': (t('clear_workspace'), self._clear_workspace),
            'reset': (t('reset_layout'), self._reset_layout),
            'settings': (t('hide_settings') if self.settings_panel.is_open() else t('show_settings'), self._toggle_settings),
            'pin': (t('pin_off') if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) else t('pin_on'), self._toggle_pin),
        }

    def _workspace_menu_order(self) -> list[str]:
        saved = self._state.settings.workspace_menu_order
        if saved:
            known = set(self._ALL_MENU_ITEMS)
            return [item_id for item_id in saved if item_id in known or item_id == '---']
        return list(self._DEFAULT_MENU_ORDER)

    def _show_workspace_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        items = self._workspace_menu_items()
        actions: dict[object, callable] = {}
        for item_id in self._workspace_menu_order():
            if item_id == '---':
                menu.addSeparator()
            elif item_id == 'appearance':
                sub = menu.addMenu(self._translator.t('appearance'))
                self._build_appearance_menu(sub)
            elif item_id in items:
                label, handler = items[item_id]
                action = menu.addAction(label)
                actions[action] = handler
        menu.addSeparator()
        # Show red dot until user has opened customize panel at least once
        dot = " 🔴" if not self._hint_manager.is_shown("hint_customize_menu") else ""
        customize_action = menu.addAction(self._translator.t('customize_order') + dot)
        actions[customize_action] = self._show_menu_order_dialog_and_dismiss_hint
        chosen = menu.exec(self.workspace.mapToGlobal(pos))
        if chosen in actions:
            actions[chosen]()

    def _tidy_workspace(self) -> None:
        for card in list(self.workspace.all_cards()):
            if card.isVisible():
                self.workspace.hide_card(card.widget_id)
        self._refresh_dock_items()
        self._schedule_save()

    def _clear_workspace(self) -> None:
        for widget_id, (card, editor) in list(self._example_cards.items()):
            editor.remove_assets()
            self.workspace.remove_card(widget_id)
            card.setParent(None)
            card.deleteLater()
        self._example_cards.clear()
        self._card_labels.clear()
        if self.prompt_card.isVisible():
            self._dock_card(self.prompt_card.widget_id)
        if self.main_card.isVisible():
            self._dock_card(self.main_card.widget_id)
        self._refresh_dock_items()
        self._schedule_save()
        self._update_token_estimate()

    def _show_menu_order_dialog(self) -> None:
        popup = self._create_popup(320)
        inner = popup._inner
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 8, 16, 12)
        layout.setSpacing(8)
        layout.addWidget(QLabel(self._translator.t('drag_to_reorder'), inner))
        list_widget = QListWidget(inner)
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        items = self._workspace_menu_items()
        current_order = self._workspace_menu_order()
        current_set = set(current_order)

        def _make_item(item_id: str, checked: bool) -> None:
            if item_id == '---':
                li = QListWidgetItem('── 分隔线 ──')
            elif item_id == 'appearance':
                li = QListWidgetItem(self._translator.t('appearance'))
            elif item_id in items:
                li = QListWidgetItem(items[item_id][0])
            else:
                return
            li.setData(Qt.ItemDataRole.UserRole, item_id)
            if item_id != '---':
                li.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            list_widget.addItem(li)

        # Items in current order (checked)
        for item_id in current_order:
            _make_item(item_id, True)

        # Items not in current order (unchecked, at the bottom)
        for item_id in self._ALL_MENU_ITEMS:
            if item_id not in current_set and item_id != '---':
                _make_item(item_id, False)

        layout.addWidget(list_widget, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(self._translator.t('cancel'), inner)
        cancel_btn.setObjectName('PopupBtn')
        ok_btn = QPushButton(self._translator.t('ok'), inner)
        ok_btn.setObjectName('PopupBtn')
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        def _accept():
            new_order = []
            for i in range(list_widget.count()):
                li = list_widget.item(i)
                item_id = li.data(Qt.ItemDataRole.UserRole)
                # Include separators and checked items
                if item_id == '---' or li.checkState() == Qt.CheckState.Checked:
                    new_order.append(item_id)
            self._state.settings.workspace_menu_order = new_order
            self._schedule_save()
            popup.close()

        ok_btn.clicked.connect(_accept)
        cancel_btn.clicked.connect(popup.close)
        self._finish_popup(popup)

    # ── Appearance menu ──

    def _build_appearance_menu(self, menu: QMenu) -> None:
        settings = self.settings_panel.settings()

        theme_menu = menu.addMenu(self._translator.t('theme'))
        for theme_id, label_key in [('dark', 'theme_dark'), ('light', 'theme_light')]:
            action = theme_menu.addAction(self._translator.t(label_key))
            action.setCheckable(True)
            action.setChecked(self._state.settings.theme == theme_id)
            action.triggered.connect(partial(self._set_theme, theme_id))
        theme_menu.addSeparator()
        custom_action = theme_menu.addAction(self._translator.t('custom_bg'))
        custom_action.setCheckable(True)
        custom_action.setChecked(self._state.settings.theme == 'custom')
        custom_action.triggered.connect(self._set_custom_bg)

        bg_settings_action = menu.addAction(self._translator.t('bg_settings'))
        bg_settings_action.triggered.connect(self._show_bg_settings_panel)

        opacity_menu = menu.addMenu(self._translator.t('card_opacity'))
        presets_opacity = (50, 65, 82, 90, 100)
        current_opacity = self._state.settings.card_opacity
        current_is_opacity_preset = current_opacity in presets_opacity
        for pct in presets_opacity:
            action = opacity_menu.addAction(f'{pct}%')
            action.setCheckable(True)
            action.setChecked(current_opacity == pct)
            action.triggered.connect(partial(self._set_card_opacity, pct))
        opacity_menu.addSeparator()
        custom_opacity_label = self._translator.t('custom_value')
        if not current_is_opacity_preset:
            custom_opacity_label += f'  ({current_opacity}%)'
        custom_opacity_action = opacity_menu.addAction(custom_opacity_label)
        custom_opacity_action.setCheckable(True)
        custom_opacity_action.setChecked(not current_is_opacity_preset)
        custom_opacity_action.triggered.connect(self._input_custom_card_opacity)

        size_menu = menu.addMenu(self._translator.t('ui_scale'))
        presets = (90, 100, 110, 125, 140, 160)
        current_is_preset = settings.ui_scale_percent in presets
        for percent in presets:
            action = size_menu.addAction(f'{percent}%')
            action.setCheckable(True)
            action.setChecked(settings.ui_scale_percent == percent)
            action.triggered.connect(partial(self._set_ui_scale, percent))
        size_menu.addSeparator()
        custom_scale_label = self._translator.t('custom_value')
        if not current_is_preset:
            custom_scale_label += f'  ({settings.ui_scale_percent}%)'
        custom_scale_action = size_menu.addAction(custom_scale_label)
        custom_scale_action.setCheckable(True)
        custom_scale_action.setChecked(not current_is_preset)
        custom_scale_action.triggered.connect(self._input_custom_ui_scale)

        font_size_menu = menu.addMenu(self._translator.t('font_size'))
        pt_presets = (10, 11, 12, 13, 14)
        current_pt_is_preset = settings.body_font_point_size in pt_presets
        for pt in pt_presets:
            action = font_size_menu.addAction(f'{pt} pt')
            action.setCheckable(True)
            action.setChecked(settings.body_font_point_size == pt)
            action.triggered.connect(partial(self._set_font_size, pt))
        font_size_menu.addSeparator()
        custom_pt_label = self._translator.t('custom_value')
        if not current_pt_is_preset:
            custom_pt_label += f'  ({settings.body_font_point_size} pt)'
        custom_pt_action = font_size_menu.addAction(custom_pt_label)
        custom_pt_action.setCheckable(True)
        custom_pt_action.setChecked(not current_pt_is_preset)
        custom_pt_action.triggered.connect(self._input_custom_font_size)

        font_menu = menu.addMenu(self._translator.t('font_style'))
        for profile_id, label_key in [
            ('default', 'font_default'),
            ('wenkai', 'font_wenkai'),
            ('yahei', 'font_yahei'),
            ('segoe', 'font_segoe'),
        ]:
            action = font_menu.addAction(self._translator.t(label_key))
            action.setCheckable(True)
            action.setChecked(settings.font_profile == profile_id)
            action.triggered.connect(partial(self._set_font_profile, profile_id, ''))

        imported = self._storage.list_imported_fonts()
        if imported:
            font_menu.addSeparator()
            for item in imported:
                font_id = item.get('id', '')
                action = font_menu.addAction(item.get('family', font_id))
                action.setCheckable(True)
                action.setChecked(settings.font_profile == 'custom' and settings.custom_font_id == font_id)
                action.triggered.connect(partial(self._set_font_profile, 'custom', font_id))

        font_menu.addSeparator()
        font_menu.addAction(self._translator.t('import_ttf')).triggered.connect(self._import_font)

        menu.addSeparator()
        menu.addAction(self._translator.t('reset_appearance')).triggered.connect(self._reset_appearance)

    def _set_custom_bg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self._translator.t('custom_bg'), '', 'Images (*.png *.jpg *.jpeg *.webp *.bmp)')
        if not path:
            return
        from .theme import extract_palette_from_image
        palette = extract_palette_from_image(path)
        self._state.settings.theme = 'custom'
        self._state.settings.custom_bg_image = path
        self._custom_palette = palette
        self._apply_background_image()
        self._apply_appearance()

    def _apply_background_image(self) -> None:
        s = self._state.settings
        if s.custom_bg_image:
            self.workspace.set_background_image(s.custom_bg_image, s.bg_blur, s.bg_opacity, s.bg_brightness)
        else:
            self.workspace.clear_background_image()

    def _set_theme(self, theme_id: str) -> None:
        self._state.settings.theme = theme_id
        self._state.settings.custom_bg_image = ''
        self._state.settings.bg_brightness = 0 if theme_id == 'dark' else 100
        self._custom_palette = None
        self.workspace.clear_background_image()
        self._apply_appearance()

    def _create_popup(self, width: int = 260, *, min_width: int = 180, min_height: int = 120) -> QWidget:
        popup = QWidget(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        popup.setMinimumSize(min_width, min_height)
        inner = QWidget(popup)
        inner.setObjectName('PopupPanel')
        inner.setMinimumWidth(min_width)

        # Inner fills popup, resizable
        popup_layout = QVBoxLayout(popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.addWidget(inner)

        popup._inner = inner
        popup._default_width = width
        popup._resizing = False
        popup._resize_edge = ""
        popup._resize_origin = QPoint()
        popup._frame_origin = QRect()

        # Resize via edges
        _EDGE_MARGIN = 6

        def _detect_edge(pos: QPoint) -> str:
            r = popup.rect()
            edges = ""
            if pos.y() >= r.height() - _EDGE_MARGIN:
                edges += "bottom"
            if pos.x() >= r.width() - _EDGE_MARGIN:
                edges += "right"
            return edges

        original_mouse_press = popup.mousePressEvent
        original_mouse_move = popup.mouseMoveEvent
        original_mouse_release = popup.mouseReleaseEvent

        def _mouse_press(event):
            edge = _detect_edge(event.pos())
            if edge and event.button() == Qt.MouseButton.LeftButton:
                popup._resizing = True
                popup._resize_edge = edge
                popup._resize_origin = event.globalPosition().toPoint()
                popup._frame_origin = QRect(popup.geometry())
            else:
                original_mouse_press(event)

        def _mouse_move(event):
            if popup._resizing:
                delta = event.globalPosition().toPoint() - popup._resize_origin
                geo = QRect(popup._frame_origin)
                if "right" in popup._resize_edge:
                    geo.setWidth(max(popup.minimumWidth(), popup._frame_origin.width() + delta.x()))
                if "bottom" in popup._resize_edge:
                    geo.setHeight(max(popup.minimumHeight(), popup._frame_origin.height() + delta.y()))
                popup.setGeometry(geo)
            else:
                edge = _detect_edge(event.pos())
                if "bottom" in edge and "right" in edge:
                    popup.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif "bottom" in edge:
                    popup.setCursor(Qt.CursorShape.SizeVerCursor)
                elif "right" in edge:
                    popup.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    popup.setCursor(Qt.CursorShape.ArrowCursor)
                original_mouse_move(event)

        def _mouse_release(event):
            popup._resizing = False
            original_mouse_release(event)

        popup.mousePressEvent = _mouse_press
        popup.mouseMoveEvent = _mouse_move
        popup.mouseReleaseEvent = _mouse_release
        popup.setMouseTracking(True)

        return popup

    def _finish_popup(self, popup: QWidget, anchor: QWidget | None = None) -> None:
        inner = popup._inner

        # Draggable header bar
        drag_bar = QWidget(inner)
        drag_bar.setFixedHeight(28)
        drag_bar.setCursor(Qt.CursorShape.OpenHandCursor)
        drag_bar._dragging = False
        drag_bar._drag_origin = QPoint()
        drag_bar._popup_origin = QPoint()

        def _bar_press(event):
            if event.button() == Qt.MouseButton.LeftButton:
                drag_bar._dragging = True
                drag_bar._drag_origin = event.globalPosition().toPoint()
                drag_bar._popup_origin = popup.pos()
                drag_bar.setCursor(Qt.CursorShape.ClosedHandCursor)

        def _bar_move(event):
            if drag_bar._dragging:
                delta = event.globalPosition().toPoint() - drag_bar._drag_origin
                popup.move(drag_bar._popup_origin + delta)

        def _bar_release(event):
            drag_bar._dragging = False
            drag_bar.setCursor(Qt.CursorShape.OpenHandCursor)

        drag_bar.mousePressEvent = _bar_press
        drag_bar.mouseMoveEvent = _bar_move
        drag_bar.mouseReleaseEvent = _bar_release

        header = QHBoxLayout(drag_bar)
        header.setContentsMargins(8, 0, 4, 0)
        header.addStretch()
        close_btn = QPushButton('×', drag_bar)
        close_btn.setObjectName('PopupClose')
        close_btn.clicked.connect(popup.close)
        header.addWidget(close_btn)

        inner.layout().insertWidget(0, drag_bar)
        inner.adjustSize()
        w = max(popup._default_width, inner.sizeHint().width())
        h = inner.sizeHint().height()
        popup.resize(w, h)

        # Position at mouse cursor
        cursor_pos = QCursor.pos()
        popup.move(cursor_pos.x() - w // 2, cursor_pos.y() - 20)
        popup.show()

    def _show_bg_settings_panel(self) -> None:
        popup = self._create_popup(260)
        inner = popup._inner
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 8, 16, 12)
        layout.setSpacing(6)

        self._bg_apply_timer = QTimer(self)
        self._bg_apply_timer.setSingleShot(True)
        self._bg_apply_timer.setInterval(80)

        t = self._translator.t
        s = self._state.settings
        for label_key, attr, default in [
            ('bg_brightness', 'bg_brightness', s.bg_brightness),
            ('bg_blur', 'bg_blur', s.bg_blur),
            ('bg_opacity', 'bg_opacity', s.bg_opacity),
        ]:
            if attr != 'bg_brightness' and not s.custom_bg_image:
                continue
            row = QHBoxLayout()
            row.addWidget(QLabel(t(label_key), inner))
            row.addStretch()
            val_lbl = QLabel(f'{default}%', inner)
            row.addWidget(val_lbl)
            layout.addLayout(row)
            slider = QSlider(Qt.Orientation.Horizontal, inner)
            slider.setRange(0, 100)
            slider.setValue(default)
            slider.valueChanged.connect(lambda v, a=attr, vl=val_lbl: self._on_bg_slider(a, v, vl))
            layout.addWidget(slider)

        self._finish_popup(popup)

    def _on_bg_slider(self, attr: str, value: int, val_label: QLabel) -> None:
        val_label.setText(f'{value}%')
        setattr(self._state.settings, attr, value)
        self._bg_apply_timer.timeout.disconnect() if self._bg_apply_timer.receivers(self._bg_apply_timer.timeout) > 0 else None
        if attr == 'bg_brightness':
            self._bg_apply_timer.timeout.connect(self._apply_appearance)
        else:
            self._bg_apply_timer.timeout.connect(self._apply_background_image)
        self._bg_apply_timer.start()
        self._schedule_save()

    def _set_bg_param(self, attr: str, value: int) -> None:
        setattr(self._state.settings, attr, value)
        self._apply_background_image()
        self._schedule_save()

    def _show_int_input_popup(self, title: str, current: int, min_val: int, max_val: int, callback) -> None:
        popup = self._create_popup(220)
        inner = popup._inner
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 8, 16, 12)
        layout.setSpacing(8)
        layout.addWidget(QLabel(title, inner))
        from PyQt6.QtWidgets import QSpinBox
        spin = QSpinBox(inner)
        spin.setRange(min_val, max_val)
        spin.setValue(current)
        layout.addWidget(spin)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton(self._translator.t('ok'), inner)
        ok_btn.setObjectName('PopupBtn')
        ok_btn.clicked.connect(lambda: (callback(spin.value()), popup.close()))
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)
        self._finish_popup(popup)

    def _input_custom_card_opacity(self) -> None:
        self._show_int_input_popup(self._translator.t('card_opacity'), self._state.settings.card_opacity, 30, 100, self._set_card_opacity)

    def _set_card_opacity(self, pct: int) -> None:
        self._state.settings.card_opacity = pct
        self._apply_appearance()

    def _set_ui_scale(self, percent: int) -> None:
        self.settings_panel.set_ui_scale(percent)
        self._apply_appearance()

    def _set_font_size(self, pt: int) -> None:
        self.settings_panel.set_font_size(pt)
        self._apply_appearance()

    def _input_custom_ui_scale(self) -> None:
        self._show_int_input_popup(self._translator.t('ui_scale'), self.settings_panel.settings().ui_scale_percent, 50, 300, self._set_ui_scale)

    def _input_custom_font_size(self) -> None:
        self._show_int_input_popup(self._translator.t('font_size'), self.settings_panel.settings().body_font_point_size, 8, 24, self._set_font_size)

    def _set_font_profile(self, profile: str, custom_id: str) -> None:
        self.settings_panel.set_font_profile(profile, custom_id)
        self._apply_appearance()

    def _import_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self._translator.t('import_ttf'), '', 'TrueType Font (*.ttf)')
        if not path:
            return
        from PyQt6.QtGui import QFontDatabase
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            return
        families = QFontDatabase.applicationFontFamilies(fid)
        family = families[0] if families else ''
        font_id, family = self._storage.import_font(path, family)
        self._set_font_profile('custom', font_id)

    def _reset_appearance(self) -> None:
        self.settings_panel.set_ui_scale(100)
        self.settings_panel.set_font_size(11)
        self.settings_panel.set_font_profile('default', '')
        self._apply_appearance()

    def _apply_appearance(self) -> None:
        settings = self.settings_panel.settings()
        app = QApplication.instance()
        if app is None:
            return
        from .theme import generate_qss, scale_qss
        theme = self._state.settings.theme or 'dark'
        opacity = self._state.settings.card_opacity
        brightness = self._state.settings.bg_brightness
        custom_family = self._storage.font_family_by_id(settings.custom_font_id) if settings.custom_font_id else ''
        # Build font_family CSS string from profile
        from .font_loader import FONT_PROFILES
        if settings.font_profile == 'custom' and custom_family:
            ff_list = [custom_family]
        else:
            ff_list = FONT_PROFILES.get(settings.font_profile, FONT_PROFILES['default'])
        font_family_css = ', '.join(f'"{f}"' for f in ff_list) + ', sans-serif'
        app.setStyleSheet(scale_qss(generate_qss(
            theme, custom_palette=self._custom_palette, card_opacity=opacity,
            brightness=brightness, body_font_pt=settings.body_font_point_size,
            font_family=font_family_css,
        ), settings.ui_scale_percent))
        app.setFont(build_body_font(settings.font_profile, settings.body_font_point_size, custom_family))
        # Notify image manager to re-apply theme
        if hasattr(self, '_image_manager') and self._image_manager is not None:
            self._image_manager.apply_theme()
        if hasattr(self, '_history_sidebar') and self._history_sidebar is not None:
            self._history_sidebar.apply_theme()
        if hasattr(self, 'dock_panel') and self.dock_panel is not None:
            self.dock_panel.apply_theme()
        if hasattr(self, 'interrogator_widget') and self.interrogator_widget is not None:
            self.interrogator_widget.apply_theme()
        # Refresh card title colors
        for card in self.workspace.all_cards():
            card.apply_theme()
        # Refresh tag category highlighter colors
        self.output_widget.refresh_highlighter()
        self._schedule_save()

    # ── Dock menu ──

    def _show_dock_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        add_example_action = menu.addAction(self._translator.t('add_example'))
        viewer_action = menu.addAction(self._translator.t('metadata_viewer'))
        destroyer_action = menu.addAction(self._translator.t('metadata_destroyer'))
        manager_action = menu.addAction(self._translator.t('image_manager'))
        chosen = menu.exec(self.dock_panel.mapToGlobal(pos))
        if chosen is add_example_action:
            self._add_example_card()
        elif chosen is viewer_action:
            self._toggle_metadata_viewer()
        elif chosen is destroyer_action:
            self._toggle_metadata_destroyer()
        elif chosen is manager_action:
            self._open_image_manager()

    def _show_input_menu(self, pos: QPoint) -> None:
        menu = self.input_widget.editor.createStandardContextMenu()
        menu.addSeparator()
        send_action = QAction(self._translator.t('stop') if self._worker is not None and self._worker.isRunning() else self._translator.t('send'), menu)
        summary_action = QAction(self._translator.t('summary'), menu)
        clear_action = QAction(self._translator.t('clear_history'), menu)
        clear_memory_action = QAction(self._translator.t('clear_memory'), menu)
        first_standard = menu.actions()[0] if menu.actions() else None
        if first_standard is not None:
            menu.insertAction(first_standard, clear_action)
            menu.insertAction(clear_action, clear_memory_action)
            menu.insertAction(clear_memory_action, summary_action)
            menu.insertAction(summary_action, send_action)
            menu.insertSeparator(send_action)
        else:
            menu.addAction(send_action)
            menu.addAction(summary_action)
            menu.addAction(clear_action)
            menu.addAction(clear_memory_action)
        chosen = menu.exec(self.input_widget.editor.mapToGlobal(pos))
        if chosen is send_action:
            self._handle_send_action()
        elif chosen is summary_action:
            self._handle_summary_action()
        elif chosen is clear_action:
            self._clear_input_history()
        elif chosen is clear_memory_action:
            self._clear_conversation_history()

    def _handle_send_action(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            return
        settings = self.settings_panel.settings()
        errors = validate_examples(self._collect_examples())
        if errors:
            self._append_error(self._translator.t('error_invalid_example'))
            return
        base_url = normalize_api_base_url(settings.api_base_url)
        if not base_url:
            self._append_error(self._translator.t('error_missing_api'), open_settings=True)
            return
        if not settings.model:
            self._append_error(self._translator.t('error_missing_model'), open_settings=True)
            return
        messages = build_messages(
            self.prompt_manager.prompt_entries(), self._collect_examples(),
            self.input_widget.text(), settings.memory_mode,
            ocs=self._library_panel.oc_entries(),
            history=self._conversation_history if settings.memory_mode else None,
        )
        if not any(message.get('role') == 'user' and message.get('content', '').strip() for message in messages):
            self._append_error(self._translator.t('error_missing_input'))
            return
        payload = {
            'model': settings.model,
            'messages': messages,
            'temperature': settings.temperature,
            'top_p': settings.top_p,
            'max_tokens': settings.max_tokens,
            'stream': settings.stream,
        }
        if settings.top_k is not None:
            payload['top_k'] = settings.top_k
        if settings.freq_penalty != 0:
            payload['frequency_penalty'] = settings.freq_penalty
        if settings.pres_penalty != 0:
            payload['presence_penalty'] = settings.pres_penalty
        self.output_widget.clear_output()
        self.main_card.show()
        self.main_card.raise_()
        user_text = self.input_widget.text().strip()
        self._pending_history_input = user_text
        self._pending_history_model = settings.model
        self.input_widget.clear_text()
        self._start_worker(f'{base_url}/chat/completions', payload, settings.api_key, stream=settings.stream, summary_mode=False)

    def _handle_summary_action(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        settings = self.settings_panel.settings()
        base_url = normalize_api_base_url(settings.api_base_url)
        if not base_url:
            self._append_error(self._translator.t('error_missing_api'), open_settings=True)
            return
        if not settings.model:
            self._append_error(self._translator.t('error_missing_model'), open_settings=True)
            return
        summary_prompt = settings.summary_prompt or self._translator.t('summary_default')
        if '{{content}}' not in summary_prompt:
            self._append_error(self._translator.t('error_summary_placeholder'), open_settings=True)
            return
        content = self.input_widget.text().strip()
        if not content:
            self._append_error(self._translator.t('error_missing_input'))
            return
        message = summary_prompt.replace('{{content}}', content)
        payload = {
            'model': settings.model,
            'messages': [{'role': 'user', 'content': message}],
            'temperature': min(1.0, settings.temperature),
            'top_p': settings.top_p,
            'max_tokens': settings.max_tokens,
            'stream': False,
        }
        if settings.top_k is not None:
            payload['top_k'] = settings.top_k
        self._start_worker(f'{base_url}/chat/completions', payload, settings.api_key, stream=False, summary_mode=True)

    def _start_worker(self, url: str, payload: dict, api_key: str, *, stream: bool, summary_mode: bool) -> None:
        if self._worker is not None:
            self._worker.blockSignals(True)
            if self._worker.isRunning():
                self._worker.cancel()
                self._worker.wait(3000)
            self._worker.deleteLater()
            self._worker = None
        self._current_mode = 'summary' if summary_mode else 'chat'
        self._worker = ChatWorker(url, payload, api_key, stream=stream, summary_mode=summary_mode, parent=self)
        self._worker.delta_received.connect(self._on_worker_delta)
        self._worker.summary_received.connect(self._on_summary_ready)
        self._worker.error_received.connect(self._on_worker_error)
        self._worker.cancelled.connect(self._on_worker_cancelled)
        self._worker.finished_cleanly.connect(self._on_worker_finished)
        self._worker.finished.connect(self._clear_worker_if_done)
        self.input_widget.set_sending(True)
        self.settings_panel.set_request_fields_disabled(True)
        self._worker.start()

    def _on_worker_delta(self, text: str) -> None:
        if self._current_mode == 'chat':
            self.output_widget.append_full_text(text)

    def _on_summary_ready(self, text: str) -> None:
        dialog = SummaryDialog(self._translator.t('summary_title'), text, self._translator.t('copy'), self)
        dialog.exec()

    def _on_worker_error(self, message: str, status_code: int, details: str) -> None:
        if self._pending_history_input and self._current_mode == 'chat':
            self.input_widget.set_text(self._pending_history_input)
            self._pending_history_input = ""
            self._pending_history_model = ""
            self._update_token_estimate()
        is_config_error = status_code == 0
        error_text = f"[Error] {message}"
        self.output_widget.append_full_text(error_text)
        if is_config_error:
            # URL/connection errors — show in output only, open settings
            if not self.settings_panel.is_open():
                self._set_settings_open(True)
        else:
            # HTTP errors (401, 502, etc.) — also generate error report
            action = 'summary' if self._current_mode == 'summary' else 'send'
            self._report_issue(
                'request_error',
                message,
                action=action,
                details=details,
                open_settings=status_code in (401, 403),
                extra_context={'status_code': status_code},
            )
        self._finish_worker_state()

    def _on_worker_cancelled(self) -> None:
        if self._pending_history_input and self._current_mode == 'chat':
            self.input_widget.set_text(self._pending_history_input)
            self._pending_history_input = ""
            self._pending_history_model = ""
            self._update_token_estimate()
        self._finish_worker_state()

    def _on_worker_finished(self) -> None:
        s = self._state.settings
        self.output_widget.apply_post_processing(
            tag_full_start=s.tag_full_start,
            tag_full_end=s.tag_full_end,
            tag_nochar_start=s.tag_nochar_start,
            tag_nochar_end=s.tag_nochar_end,
        )
        # Capture to history
        if self._current_mode == 'chat' and self._pending_history_input:
            output_text = self.output_widget.full_editor.toPlainText().strip()
            nochar_text = self.output_widget.nochar_editor.toPlainText().strip()
            if output_text:
                if self.settings_panel.settings().memory_mode:
                    self._conversation_history.append({'role': 'user', 'content': self._pending_history_input})
                    self._conversation_history.append({'role': 'assistant', 'content': output_text})
                    self._trim_conversation_history()
                from datetime import datetime
                from .models import HistoryEntry
                entry = HistoryEntry(
                    input_text=self._pending_history_input,
                    output_text=output_text,
                    nochar_text=nochar_text,
                    timestamp=datetime.now().isoformat(timespec='seconds'),
                    model=self._pending_history_model,
                )
                self._history_sidebar.add_entry(entry)
            self._pending_history_input = ""
            self._pending_history_model = ""
        self._finish_worker_state()

    def _clear_worker_if_done(self) -> None:
        if self._worker is not None and not self._worker.isRunning():
            self._worker.deleteLater()
            self._worker = None

    def _finish_worker_state(self) -> None:
        self.input_widget.set_sending(False)
        self.settings_panel.set_request_fields_disabled(False)
        self._schedule_save()

    def _should_emit_report(self, dedupe_key: str | None, dedupe_seconds: float) -> bool:
        if not dedupe_key or dedupe_seconds <= 0:
            return True
        now = time.monotonic()
        previous = self._report_cooldowns.get(dedupe_key)
        if previous is not None and now - previous < dedupe_seconds:
            return False
        self._report_cooldowns[dedupe_key] = now
        return True

    def _traceback_details(self, exc: Exception) -> str:
        details = traceback.format_exc().strip()
        if details and details != 'NoneType: None':
            return details
        return f'{type(exc).__name__}: {exc}'

    def _build_error_context(self, action: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {'request_mode': self._current_mode}
        if extra:
            payload.update(extra)
        return safe_context_from_settings(self.settings_panel.settings(), action=action, extra=payload)

    def _report_issue(
        self,
        kind: str,
        message: str,
        *,
        action: str,
        details: str = '',
        open_settings: bool = False,
        extra_context: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
        dedupe_seconds: float = 0.0,
    ) -> None:
        if not self._should_emit_report(dedupe_key, dedupe_seconds):
            return
        self._append_error(message, open_settings=open_settings)
        settings = self.settings_panel.settings()
        report = report_error(
            self._storage,
            kind=kind,
            summary=message,
            details=details,
            context=self._build_error_context(action, extra_context),
            translator=self._translator,
            parent=self,
            popup=True,
            api_base_url=settings.api_base_url,
            api_key=settings.api_key,
        )
        if report.report_path:
            self.input_widget.append_status_line(
                self._translator.t('error_report_saved').format(path=report.report_path)
            )

    def _append_error(self, message: str, *, open_settings: bool = False) -> None:
        self.input_widget.append_status_line(f"{self._translator.t('error_prefix')} {message}")
        if open_settings and not self.settings_panel.is_open():
            self._set_settings_open(True)

    def _update_token_estimate(self) -> None:
        settings = self.settings_panel.settings()
        messages = build_messages(
            self.prompt_manager.prompt_entries(), self._collect_examples(),
            self.input_widget.text(), settings.memory_mode,
            ocs=self._library_panel.oc_entries(),
            history=self._conversation_history if settings.memory_mode else None,
        )
        estimated = estimate_messages_tokens(messages)
        self.input_widget.set_token_estimate(estimated, settings.max_tokens)

    def _fetch_models(self) -> None:
        base_url = (self.settings_panel.api_base_url.text().strip()).rstrip('/')
        api_key = self.settings_panel.api_key.text().strip()
        if not base_url:
            return
        try:
            import requests
            headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
            resp = requests.get(f'{base_url}/models', headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = sorted(m['id'] for m in data.get('data', []) if 'id' in m)
        except Exception:
            return
        if not models:
            return
        combo = self.settings_panel.model_combo
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(models)
        combo.setCurrentText(current)
        combo.blockSignals(False)
        combo.showPopup()

    def _export_prompts(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self._translator.t('export_prompts'), 'prompts.json', 'JSON (*.json)')
        if not path:
            return
        try:
            self._storage.export_prompts(self.prompt_manager.prompt_entries(), path)
        except Exception as exc:
            self._report_issue(
                'storage_error',
                self._translator.t('error_export_prompts_failed'),
                action='export_prompts',
                details=self._traceback_details(exc),
                extra_context={'target_file': Path(path).name},
            )

    def _import_prompts(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self._translator.t('import_prompts'), '', 'JSON (*.json)')
        if not path:
            return
        try:
            prompts = self._storage.import_prompts(path)
        except ValueError as exc:
            self._report_issue(
                'import_error',
                self._translator.t('invalid_prompt_file'),
                action='import_prompts',
                details=self._traceback_details(exc),
                extra_context={'source_file': Path(path).name},
            )
            return
        except Exception as exc:
            self._report_issue(
                'import_error',
                self._translator.t('error_import_prompts_failed'),
                action='import_prompts',
                details=self._traceback_details(exc),
                extra_context={'source_file': Path(path).name},
            )
            return
        self.prompt_manager.set_prompt_entries(prompts)
        self._update_token_estimate()
        self._schedule_save()

    def _export_config_bundle(self, scopes: str | list[str]) -> None:
        normalized_scopes = self._normalize_config_scopes(scopes)
        if not normalized_scopes:
            return
        default_name = self._config_filename_for_scope(normalized_scopes)
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.t('export_config'),
            default_name,
            'HainTag Config (*.aitg.json *.json)',
        )
        if not path:
            return
        try:
            current_state = self._build_app_state()
            self._storage.export_config_bundle(
                path,
                normalized_scopes,
                settings=current_state.settings,
                prompts=current_state.prompts,
                examples=current_state.examples,
                dock=current_state.dock,
                widgets=current_state.widgets,
                window=current_state.window,
                artists=self._library_panel.artist_entries(),
                ocs=self._library_panel.oc_entries(),
                history=self._storage.load_history(),
            )
        except Exception as exc:
            self._report_issue(
                'storage_error',
                self._translator.t('error_export_config_failed'),
                action='export_config',
                details=self._traceback_details(exc),
                extra_context={'scope': normalized_scopes, 'target_file': Path(path).name},
            )

    def _import_config_bundle(self, scopes: str | list[str]) -> None:
        normalized_scopes = self._normalize_config_scopes(scopes)
        if not normalized_scopes:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.t('import_config'),
            '',
            'HainTag Config (*.aitg.json *.json)',
        )
        if not path:
            return
        try:
            bundle = self._storage.import_config_bundle(path)
            current_state = self._build_app_state()
            imported_state = self._storage.state_from_bundle(bundle, current_state, normalized_scopes)
            self._apply_full_profile_state(imported_state)

            artists, ocs = self._storage.library_from_bundle(
                bundle,
                self._library_panel.artist_entries(),
                self._library_panel.oc_entries(),
                normalized_scopes,
            )
            if CONFIG_SCOPE_ARTIST_LIBRARY in normalized_scopes or CONFIG_SCOPE_OC_LIBRARY in normalized_scopes:
                self._library_panel.set_entries(artists, ocs)
                self._storage.save_library(artists, ocs)

            history_entries = self._storage.history_from_bundle(
                bundle,
                self._storage.load_history(),
                normalized_scopes,
            )
            if CONFIG_SCOPE_HISTORY in normalized_scopes:
                self._storage.save_history(history_entries)
                self._history_sidebar.set_entries(history_entries)
        except ValueError as exc:
            self._report_issue(
                'import_error',
                self._translator.t('invalid_config_file'),
                action='import_config',
                details=self._traceback_details(exc),
                extra_context={'scope': normalized_scopes, 'source_file': Path(path).name},
            )
            return
        except Exception as exc:
            self._report_issue(
                'import_error',
                self._translator.t('error_import_config_failed'),
                action='import_config',
                details=self._traceback_details(exc),
                extra_context={'scope': normalized_scopes, 'source_file': Path(path).name},
            )
            return

    def _change_language(self, language: str) -> None:
        previous = self._translator.get_language()
        self._translator.set_language(language)
        if previous == self._translator.get_language():
            return
        self._label_card(self.prompt_card, 'widget_prompts')
        self._label_card(self.main_card, 'widget_main')
        self._label_card(self.metadata_viewer_card, 'widget_metadata_viewer')
        self._label_card(self.metadata_destroyer_card, 'widget_metadata_destroyer')
        self._label_card(self.interrogator_card, 'interrogator')
        self.interrogator_widget.retranslate_ui()
        self._history_sidebar.retranslate_ui()
        self._history_tab_btn.setToolTip(self._translator.t("history_panel"))
        for index, widget_id in enumerate(sorted(self._example_cards), start=1):
            label = f"{self._translator.t('example')} {index}"
            self._card_labels[widget_id] = label
            self._example_cards[widget_id][0].set_title(label)
        self._retranslate_ui()
        self._update_token_estimate()
        self._schedule_save()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._translator.t('app_title'))
        self.btn_settings.setToolTip(self._translator.t('settings'))
        self.btn_gallery.setToolTip(self._translator.t('image_manager'))
        self.btn_help.setToolTip(self._translator.t('shortcuts'))
        self.btn_pin.setToolTip(self._translator.t('pin'))
        self.btn_min.setToolTip(self._translator.t('minimize'))
        self.btn_max.setToolTip(self._translator.t('maximize'))
        self.btn_close.setToolTip(self._translator.t('close'))
        grip_title = self._translator.t('grip_title')
        resize_title = self._translator.t('resize_title')
        close_title = self._translator.t('tip_close_card')
        self.prompt_card.retranslate_ui(grip_title, resize_title, close_title)
        self.main_card.retranslate_ui(grip_title, resize_title, close_title)
        self.prompt_manager.retranslate_ui()
        self.input_widget.retranslate_ui()
        self.settings_panel.retranslate_ui()
        self.dock_panel.set_close_label(self._translator.t('close'))
        self._lib_tab_btn.setToolTip(self._translator.t('tip_library'))
        for card, editor in self._example_cards.values():
            card.retranslate_ui(grip_title, resize_title, close_title)
            editor.retranslate_ui()
        self._refresh_dock_items()

    def _add_example_card(self) -> None:
        self._create_example_card(ExampleEntry())
        latest_card = self.workspace.card(f'widget-example-{self._next_example_index - 1}')
        if latest_card is not None:
            latest_card.show()
            latest_card.setGeometry(self.workspace.find_free_position(QSize(360, 320), exclude=latest_card))
            self.workspace.resolve_overlap(latest_card)
        self._update_token_estimate()

    def _toggle_metadata_viewer(self) -> None:
        card = self.metadata_viewer_card
        if card.isVisible():
            card.hide()
        else:
            card.show()
            if card.x() == 0 and card.y() == 0:
                card.setGeometry(self.workspace.find_free_position(QSize(400, 360), exclude=card))
            self.workspace.resolve_overlap(card)
        self._refresh_dock_items()
        self._schedule_save()

    def _toggle_metadata_destroyer(self) -> None:
        card = self.metadata_destroyer_card
        if card.isVisible():
            card.hide()
        else:
            card.show()
            if card.x() == 0 and card.y() == 0:
                card.setGeometry(self.workspace.find_free_position(QSize(380, 300), exclude=card))
            self.workspace.resolve_overlap(card)
        self._refresh_dock_items()
        self._schedule_save()

    def _on_tagger_model_dir_changed(self, path: str) -> None:
        self._state.settings.tagger_model_dir = path
        self._schedule_save()

    def _on_tagger_python_path_changed(self, path: str) -> None:
        self._state.settings.tagger_python_path = path
        self._schedule_save()

    def _toggle_interrogator(self) -> None:
        card = self.interrogator_card
        if card.isVisible():
            card.hide()
        else:
            # Update API settings for LLM tab
            s = self.settings_panel.settings()
            from .logic import normalize_api_base_url
            self.interrogator_widget.set_api_settings(
                normalize_api_base_url(s.api_base_url), s.api_key, s.model
            )
            card.show()
            if card.x() == 0 and card.y() == 0:
                card.setGeometry(self.workspace.find_free_position(QSize(440, 520), exclude=card))
            self.workspace.resolve_overlap(card)
        self._refresh_dock_items()
        self._schedule_save()

    def _open_image_manager(self) -> None:
        if hasattr(self, '_image_manager') and self._image_manager is not None:
            self._image_manager.show()
            self._image_manager.raise_()
            self._image_manager.activateWindow()
            return
        initial_folder = self._state.settings.image_manager_folder
        self._image_manager = ImageManagerWindow(self._translator, initial_folder, self._storage, self)
        self._image_manager.send_to_input.connect(self._on_image_manager_send)
        self._image_manager.use_as_example.connect(self._on_image_manager_example)
        self._image_manager.folder_changed.connect(self._on_image_manager_folder)
        self._image_manager.show()
        self._image_manager.load_initial_folder()

    def _on_image_manager_send(self, prompt: str) -> None:
        self.input_widget.editor.setPlainText(prompt)

    def _on_image_manager_example(self, path: str) -> None:
        entry = ExampleEntry(image_path=path)
        self._create_example_card(entry)

    def _on_image_manager_folder(self, folder: str) -> None:
        self._state.settings.image_manager_folder = folder
        self._schedule_save()

    def _toggle_library(self) -> None:
        self._library_open = not self._library_open
        if self._library_open:
            self._library_panel.show()
            self._library_panel.apply_theme()
            self._lib_tab_btn.setText("▸")
        else:
            self._library_panel.hide()
            self._lib_tab_btn.setText("◂")
        self._position_library()

    def _position_library(self) -> None:
        """Position the library tab button and panel within the workspace."""
        ws_w = self.workspace.width()
        ws_h = self.workspace.height()
        btn = self._lib_tab_btn
        if self._library_open:
            pw = self._library_panel.maximumWidth()
            self._library_panel.move(ws_w - pw, 0)
            self._library_panel.setFixedHeight(ws_h)
            self._library_panel.raise_()
            btn.move(ws_w - pw - btn.width(), 40)
        else:
            btn.move(ws_w - btn.width(), 40)
        btn.raise_()

    def _on_library_changed(self) -> None:
        self._storage.save_library(
            self._library_panel.artist_entries(),
            self._library_panel.oc_entries(),
        )

    def _start_onboarding(self) -> None:
        from .widgets.onboarding import OnboardingOverlay, OnboardingStep
        t = self._translator.t
        overlay = OnboardingOverlay(self.surface, self._translator)
        overlay.finished.connect(self._register_hints)
        overlay.set_steps([
            OnboardingStep(None, t("tour_welcome_title"), t("tour_welcome_desc")),
            OnboardingStep(self.btn_settings, t("tour_settings_title"), t("tour_settings_desc"), "below"),
            OnboardingStep(self.main_card, t("tour_workbench_title"), t("tour_workbench_desc"), "right"),
            OnboardingStep(self.prompt_card, t("tour_prompts_title"), t("tour_prompts_desc"), "right"),
            OnboardingStep(self._lib_tab_btn, t("tour_library_title"), t("tour_library_desc"), "left"),
            OnboardingStep(self.btn_help, t("tour_shortcuts_title"), t("tour_shortcuts_desc"), "below"),
        ])
        overlay.start()

    def _register_hints(self) -> None:
        """Register first-time-use hint bubbles on key widgets."""
        h = self._hint_manager
        h.register(self.input_widget.send_button, "hint_send",
                   "hint_send", position="above", delay_ms=2000)
        h.register(self.prompt_manager.preview_button, "hint_preview",
                   "hint_preview", position="above", delay_ms=3000)
        h.register(self.btn_help, "hint_help",
                   "hint_help", position="below", delay_ms=4000)
        h.register(self.output_widget.full_editor, "hint_scrub",
                   "hint_scrub", position="above", delay_ms=5000)
        h.register(self._lib_tab_btn, "hint_library",
                   "hint_library", position="left", delay_ms=6000)

    def _on_history_fill(self, output_text: str, nochar_text: str) -> None:
        self.output_widget.set_full_tags(output_text)
        if nochar_text:
            self.output_widget.nochar_editor.setPlainText(nochar_text)
        self.main_card.show()
        self.main_card.raise_()

    def _toggle_history_sidebar(self) -> None:
        self._history_open = not self._history_open
        if self._history_open:
            self._history_sidebar.apply_theme()
            # If card is floating, sidebar must also be a top-level window
            if self.main_card._floating:
                self._history_sidebar.setParent(None)
                self._history_sidebar.setWindowFlags(
                    Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                    Qt.WindowType.WindowStaysOnTopHint
                )
            self._history_sidebar.animate_show()
            self._history_tab_btn.setText("▷")
        else:
            self._history_sidebar.animate_hide()
            self._history_tab_btn.setText("◁")
            # Return sidebar to workspace if it was floating
            if self._history_sidebar.parent() is None:
                QTimer.singleShot(250, lambda: self._history_sidebar.setParent(self.workspace))
        self._position_history_sidebar()

    def _position_history_btn(self) -> None:
        """Position the history tab button just outside the right edge of main_card."""
        card = self.main_card
        btn = self._history_tab_btn
        if not card.isVisible():
            btn.hide()
            if self._history_open:
                self._history_sidebar.hide()
            return
        btn.show()
        if btn.parent() is card:
            # Floating mode: button is card's child, inside right edge
            x = card.width() - btn.width()
            y = (card.height() - btn.height()) // 2
        else:
            # Workspace mode: button is workspace's child, position in workspace coords
            x = card.x() + card.width()
            y = card.y() + (card.height() - btn.height()) // 2
        btn.move(x, y)
        btn.raise_()

    def _reparent_history_btn_to_card(self) -> None:
        """Move history button to be a child of main_card (for floating mode)."""
        btn = self._history_tab_btn
        btn.setParent(self.main_card)
        btn.show()
        self._position_history_btn()
        # Also reparent sidebar as independent window next to the card
        if self._history_open:
            self._history_sidebar.setParent(None)
            self._history_sidebar.setWindowFlags(
                Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self._history_sidebar.show()
            self._position_history_sidebar()

    def _reparent_history_btn_to_workspace(self) -> None:
        """Move history button back to workspace (when card returns from floating)."""
        btn = self._history_tab_btn
        btn.setParent(self.workspace)
        btn.show()
        # Return sidebar to workspace
        if self._history_open:
            self._history_sidebar.setParent(self.workspace)
            self._history_sidebar.show()
        QTimer.singleShot(50, self._position_history_btn)
        QTimer.singleShot(50, self._position_history_sidebar)

    def _on_main_card_visibility_changed(self) -> None:
        """Called when main_card is docked/restored."""
        QTimer.singleShot(50, self._position_history_btn)

    def _position_history_sidebar(self) -> None:
        """Position the history sidebar next to main_card."""
        if not self._history_open:
            return
        card = self.main_card
        btn = self._history_tab_btn
        sidebar = self._history_sidebar
        sidebar.setFixedHeight(card.height())

        if card._floating:
            # Floating: sidebar is a top-level window, use global coords
            card_global = card.mapToGlobal(card.rect().topRight())
            sidebar.move(card_global.x(), card_global.y())
        else:
            # Workspace: sidebar is a workspace child
            sidebar_x = card.x() + card.width() + btn.width()
            sidebar_y = card.y()
            sidebar.move(sidebar_x, sidebar_y)
        sidebar.raise_()

    def _show_menu_order_dialog_and_dismiss_hint(self) -> None:
        self._hint_manager.dismiss("hint_customize_menu")
        self._show_menu_order_dialog()

    def _show_shortcuts_panel(self) -> None:
        from .widgets.shortcuts_panel import ShortcutsPanel
        from PyQt6.QtGui import QCursor
        panel = ShortcutsPanel(self._translator, parent=self)
        panel.show_at(QCursor.pos())

    def _show_prompt_preview(self) -> None:
        """Show a preview of the fully assembled prompt."""
        from .logic import build_messages
        settings = self.settings_panel.settings()
        messages = build_messages(
            self.prompt_manager.prompt_entries(),
            self._collect_examples(),
            self.input_widget.text(),
            settings.memory_mode,
            ocs=self._library_panel.oc_entries(),
            history=self._conversation_history if settings.memory_mode else None,
        )
        from .widgets.prompt_preview import PromptPreviewPopup
        popup = PromptPreviewPopup(self)
        popup.set_messages(messages, self._translator.t("prompt_preview"))
        btn = self.prompt_manager.preview_button
        btn_global = btn.mapToGlobal(QPoint(btn.width() // 2, 0))
        popup.show_at(btn_global)

    def _show_changelog(self) -> None:
        """Show changelog in a styled popup at the version label."""
        import sys
        # Find CHANGELOG.md — check project root first, then bundled resources
        candidates = [
            Path(__file__).resolve().parent.parent / "CHANGELOG.md",
            Path(getattr(sys, '_MEIPASS', '')) / "CHANGELOG.md" if hasattr(sys, '_MEIPASS') else None,
        ]
        content = ""
        for p in candidates:
            if p and p.exists():
                try:
                    content = p.read_text(encoding="utf-8")
                except OSError:
                    pass
                break
        if not content:
            content = "No changelog found."

        # Styled popup
        from .theme import current_palette
        pal = current_palette()
        popup = QWidget(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        surface = QWidget(popup)
        surface.setObjectName("ChangelogSurface")
        surface.setStyleSheet(f"""
            #ChangelogSurface {{
                background: {pal['bg']};
                border: 1px solid {pal['line_strong']};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(surface)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        from ._version import __version__
        title = QLabel(f"HainTag  v{__version__}", surface)
        title.setStyleSheet(f"color: {pal['text']}; font-size: {_fs('fs_13')}; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # Parse markdown content — simple rendering
        text_edit = QTextEdit(surface)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(content)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {pal['bg_content']};
                color: {pal['text_muted']};
                border: 1px solid {pal['line']};
                border-radius: 4px;
                padding: 8px;
                font-size: {_fs('fs_11')};
            }}
        """)
        text_edit.setMinimumHeight(300)
        layout.addWidget(text_edit)

        root_layout = QVBoxLayout(popup)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(surface)
        popup.setFixedSize(400, 420)

        # Position above the version label
        lbl_pos = self._version_label.mapToGlobal(QPoint(
            self._version_label.width() - 400,
            -424))
        popup.move(lbl_pos)
        popup.show()

    def _on_workspace_image_dropped(self, path: str) -> None:
        card = self.metadata_viewer_card
        if not card.isVisible():
            card.show()
            if card.x() == 0 and card.y() == 0:
                card.setGeometry(self.workspace.find_free_position(QSize(400, 360), exclude=card))
            self.workspace.resolve_overlap(card)
            self._refresh_dock_items()
        self.metadata_viewer_widget.load_image(path)
        self._schedule_save()

    def moveEvent(self, event) -> None:
        if not self.isMaximized():
            self._normal_geometry.moveTopLeft(self.geometry().topLeft())
        super().moveEvent(event)

    def paintEvent(self, event) -> None:
        # Paint near-invisible border so Windows sends WM_NCHITTEST to the resize zone.
        # Alpha must be high enough for DWM to register the pixels (alpha=1 is unreliable).
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 12))
        m = WINDOW_SURFACE_MARGIN
        w, h = self.width(), self.height()
        painter.drawRect(0, 0, w, m)
        painter.drawRect(0, h - m, w, m)
        painter.drawRect(0, m, m, h - 2 * m)
        painter.drawRect(w - m, m, m, h - 2 * m)
        painter.end()

    def resizeEvent(self, event) -> None:
        if not self.isMaximized():
            self._normal_geometry = QRect(self.geometry())
        self._apply_shell_layout()
        if self._startup_complete:
            for card in self.workspace.visible_cards():
                self.workspace.clamp_card(card)
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_native_window_style()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.title_bar:
            return self._handle_title_bar_event(event)
        if watched is self._destroy_combo and event.type() == QEvent.Type.ContextMenu:
            self._show_destroy_template_menu(event.globalPos())
            return True
        return super().eventFilter(watched, event)

    def nativeEvent(self, eventType, message):
        if sys.platform != 'win32':
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except (TypeError, ValueError, OSError):
            return False, 0
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            # Tell Windows the entire window is client area (no non-client border)
            return True, 0
        if self.isMaximized() or msg.message != WM_NCHITTEST:
            return False, 0
        # Use QCursor.pos() instead of lParam to get DPI-correct logical coordinates
        global_pos = QCursor.pos()
        hit = self._window_resize_hit_test(global_pos)
        if hit is None:
            return False, 0
        return True, hit

    def _window_resize_hit_test(self, global_pos: QPoint) -> int | None:
        local_pos = self.mapFromGlobal(global_pos)
        if not self.rect().contains(local_pos):
            return None
        band = max(WINDOW_VISIBLE_RESIZE_BAND, WINDOW_EDGE_GAP)
        left = local_pos.x() <= band
        right = local_pos.x() >= self.width() - 1 - band
        top = local_pos.y() <= band
        bottom = local_pos.y() >= self.height() - 1 - band
        if not any((left, right, top, bottom)):
            return None
        # Only yield to dock/card resize handles, not general widgets
        if self.dock_panel.is_resize_hotspot_at(global_pos):
            return None
        if self.workspace.is_card_resize_hotspot_at(global_pos):
            return None
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return None

    def _visible_shell_regions(self) -> list[QRect]:
        regions: list[QRect] = []
        for widget in (self.surface,):
            if widget.isVisible() and widget.width() > 0 and widget.height() > 0:
                regions.append(widget.geometry())
        if regions:
            return regions
        fallback = self.rect().adjusted(
            WINDOW_SURFACE_MARGIN,
            WINDOW_SURFACE_MARGIN,
            -WINDOW_SURFACE_MARGIN,
            -WINDOW_SURFACE_MARGIN,
        )
        return [fallback]

    def _point_within_horizontal_shell_span(self, x: int, regions: list[QRect], band: int) -> bool:
        return any(region.left() - band <= x <= region.right() + band for region in regions)

    def _point_within_vertical_shell_span(self, y: int, regions: list[QRect], band: int) -> bool:
        return any(region.top() - band <= y <= region.bottom() + band for region in regions)

    def _blocks_window_resize_at(self, global_pos: QPoint) -> bool:
        if self.dock_panel.is_resize_hotspot_at(global_pos):
            return True
        if self.workspace.is_card_resize_hotspot_at(global_pos):
            return True
        widget = QApplication.widgetAt(global_pos)
        if widget is None:
            return False
        if widget is not self and not self.isAncestorOf(widget):
            return False
        current = widget
        while current is not None and current is not self:
            if current.objectName() in {'TitleBarButton', 'CloseButton', 'WidgetResizeHandle'}:
                return True
            if isinstance(current, (QAbstractButton, QLineEdit, QTextEdit, QComboBox, QAbstractSpinBox, QAbstractSlider, QScrollBar, QAbstractItemView, QMenu)):
                return True
            current = current.parentWidget()
        return False

    def _handle_title_bar_event(self, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            if self.title_bar.childAt(event.position().toPoint()) is None:
                self._toggle_maximize()
                return True
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if self.title_bar.childAt(event.position().toPoint()) is not None:
                return False
            handle = self.windowHandle()
            start_system_move = getattr(handle, 'startSystemMove', None) if handle is not None else None
            if callable(start_system_move) and not self.isMaximized() and start_system_move():
                return True
            self._title_drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.title_bar.setCursor(Qt.CursorShape.ClosedHandCursor)
            return True
        if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
            if self._title_drag_offset.isNull() or self.isMaximized():
                return False
            self.move(event.globalPosition().toPoint() - self._title_drag_offset)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and self._title_drag_offset != QPoint():
            self._title_drag_offset = QPoint()
            self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)
            return True
        return False

    def closeEvent(self, event) -> None:
        self._persist_state()
        self.metadata_destroyer_widget.cleanup_temp()
        if self._worker is not None and self._worker.isRunning():
            self._worker.blockSignals(True)
            self._worker.cancel()
            self._worker.wait(5000)
        super().closeEvent(event)

    # ── Auto Update ──

    def _check_update_auto(self) -> None:
        """Auto-check on startup (respects skipped_version)."""
        settings = self.settings_panel.settings()
        from ._version import __version__
        from .updater import UpdateChecker
        self._update_checker = UpdateChecker(__version__, self)
        self._update_checker.update_available.connect(
            lambda ver, cl, url: self._show_update_dialog(ver, cl, url, auto=True)
        )
        # no_update and check_error: silent on auto
        self._update_checker.start()

    def check_update_manual(self) -> None:
        """Manual check from settings panel (ignores skipped_version)."""
        from ._version import __version__
        from .updater import UpdateChecker
        self._update_checker = UpdateChecker(__version__, self)
        self._update_checker.update_available.connect(
            lambda ver, cl, url: self._show_update_dialog(ver, cl, url, auto=False)
        )
        self._update_checker.no_update.connect(self._show_no_update)
        self._update_checker.start()

    def _show_update_dialog(self, version: str, changelog: str,
                            download_url: str, auto: bool) -> None:
        settings = self.settings_panel.settings()
        from .updater import _parse_version
        if auto and settings.skipped_version:
            if _parse_version(version) <= _parse_version(settings.skipped_version):
                return
        from .updater import UpdateDialog
        dialog = UpdateDialog(version, changelog, download_url, self._translator, self)
        dialog.exec()
        if dialog.result_action == UpdateDialog.SKIP:
            self._state.settings.skipped_version = version.lstrip("vV")
            self._schedule_save()

    def _show_no_update(self) -> None:
        from ._version import __version__
        from .updater import NoUpdateDialog
        dialog = NoUpdateDialog(__version__, self._translator, self)
        dialog.exec()

    # ── Destroy Templates ──

    _DEFAULT_DESTROY_TEMPLATES = [
        {"name": "哈基米", "text": "哈基米哦南北绿豆~阿西嘎哈椰果奶龙~"},
        {"name": "空白", "text": ""},
        {"name": "Rick Roll", "text": "Never gonna give you up, never gonna let you down"},
    ]

    def _load_destroy_templates(self) -> None:
        """Load destroy templates into the combo box."""
        templates = self._state.settings.destroy_templates
        if not templates:
            templates = list(self._DEFAULT_DESTROY_TEMPLATES)
            self._state.settings.destroy_templates = templates
        active = self._state.settings.active_destroy_template
        self._destroy_combo.blockSignals(True)
        self._destroy_combo.clear()
        for t in templates:
            self._destroy_combo.addItem(t["name"], t["text"])
        # Select active
        idx = 0
        if active:
            for i, t in enumerate(templates):
                if t["name"] == active:
                    idx = i
                    break
        self._destroy_combo.setCurrentIndex(idx)
        self._destroy_combo.blockSignals(False)
        self._on_destroy_template_changed(idx)

    def _on_destroy_template_changed(self, index: int) -> None:
        text = self._destroy_combo.itemData(index)
        self.metadata_destroyer_widget._destroy_text = text if text else None
        name = self._destroy_combo.itemText(index)
        self._state.settings.active_destroy_template = name
        self._schedule_save()

    def _position_destroy_combo(self) -> None:
        card = self.metadata_destroyer_card
        combo = self._destroy_combo
        close_btn = card._close_btn
        # Position: left of close button
        cy = max(0, (card._drag_strip.height() - combo.height()) // 2)
        combo.move(close_btn.x() - combo.width() - 4, cy)

    def _show_destroy_template_menu(self, pos) -> None:
        self._open_destroy_template_editor()

    def _open_destroy_template_editor(self) -> None:
        from .widgets.destroy_template_editor import DestroyTemplateEditor
        templates = list(self._state.settings.destroy_templates or self._DEFAULT_DESTROY_TEMPLATES)
        active = self._destroy_combo.currentIndex()
        dialog = DestroyTemplateEditor(templates, active, self._translator, self)
        if dialog.exec():
            self._state.settings.destroy_templates = dialog.templates()
            self._load_destroy_templates()
            self._schedule_save()















