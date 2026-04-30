"""Image Interrogator — local tagger + LLM vision tag inference."""
from __future__ import annotations

import base64
import os
import sys
from functools import partial
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor, QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from ..i18n import Translator
from ..theme import _fs, current_palette, is_theme_light
from ..ui_tokens import _dp


# ═══════════════════════════════════════════════════
#  Local Tagger Tab
# ═══════════════════════════════════════════════════

class _LocalTaggerTab(QWidget):
    """Tab for local cl_tagger ONNX inference. Two states: setup guide / inference."""

    send_to_input = pyqtSignal(str)
    model_dir_changed = pyqtSignal(str)
    python_path_changed = pyqtSignal(str)

    def __init__(self, translator: Translator, parent=None,
                 model_dir: str = "", python_path: str = ""):
        super().__init__(parent)
        self._t = translator
        self._engine = None
        self._worker = None
        self._image_path: str | None = None
        self._custom_model_dir: str = model_dir
        self._external_python: str = python_path
        self._all_tags_str: str = ""

        from ..tagger import CATEGORY_NAMES, DEFAULT_ENABLED_CATEGORIES, DEFAULT_BLACKLIST
        self._enabled_categories = set(DEFAULT_ENABLED_CATEGORIES)
        self._blacklist = list(DEFAULT_BLACKLIST)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        # ── Page 0: Setup Guide ──
        self._setup_page = self._build_setup_page()
        self._stack.addWidget(self._setup_page)

        # ── Page 1: Inference ──
        self._ready_page = self._build_ready_page()
        self._stack.addWidget(self._ready_page)

        # ── Try auto-load (no dependency gate, try and show guide on failure) ──
        self._try_auto_load()

    # ───────────────── Setup Page ─────────────────

    def _build_setup_page(self) -> QWidget:
        p = current_palette()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(_dp(24), _dp(32), _dp(24), _dp(24))
        layout.setSpacing(_dp(16))

        title = QLabel(self._t.t("interr_setup_title"), page)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_14')}; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(self._t.t("interr_setup_desc"), page)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')};")
        layout.addWidget(desc)

        layout.addSpacing(_dp(8))

        steps = QLabel(self._t.t("interr_setup_steps"), page)
        steps.setWordWrap(True)
        steps.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_10')}; "
            f"background: {p['bg_surface']}; border: 1px solid {p['line']}; "
            f"border-radius: 6px; padding: 16px;"
        )
        layout.addWidget(steps)

        layout.addSpacing(_dp(8))

        # Buttons
        link_btn = QPushButton(self._t.t("interr_open_download"), page)
        link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_btn.setStyleSheet(
            f"background: transparent; color: {p['accent_text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 8px 20px; font-size: {_fs('fs_10')};"
        )
        link_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://huggingface.co/cella110n/cl_tagger/tree/main/cl_tagger_1_02")
        ))
        layout.addWidget(link_btn)

        select_btn = QPushButton(self._t.t("interr_select_model_dir"), page)
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 8px 20px; font-size: {_fs('fs_11')}; font-weight: bold;"
        )
        select_btn.clicked.connect(self._browse_model_dir)
        layout.addWidget(select_btn)

        # Auto-setup button (always available)
        self._auto_setup_btn = QPushButton(self._t.t("interr_auto_setup"), page)
        self._auto_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auto_setup_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 8px 20px; font-size: {_fs('fs_10')}; font-weight: bold;"
        )
        self._auto_setup_btn.clicked.connect(self._start_env_setup)
        layout.addWidget(self._auto_setup_btn)

        # Manual Python path button (always available)
        manual_btn = QPushButton(self._t.t("interr_manual_python"), page)
        manual_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manual_btn.setStyleSheet(
            f"background: transparent; color: {p['text_dim']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px 16px; font-size: {_fs('fs_9')};"
        )
        manual_btn.clicked.connect(self._browse_python)
        layout.addWidget(manual_btn)

        # Progress bar (hidden until download starts)
        self._setup_progress = QProgressBar(page)
        self._setup_progress.setRange(0, 100)
        self._setup_progress.setFixedHeight(_dp(16))
        self._setup_progress.hide()
        layout.addWidget(self._setup_progress)

        self._setup_status = QLabel("", page)
        self._setup_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_status.setWordWrap(True)
        self._setup_status.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        layout.addWidget(self._setup_status)

        # "Start" button — only visible when both model + python are ready
        self._start_ready_btn = QPushButton(self._t.t("interr_start_using"), page)
        self._start_ready_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_ready_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 10px 20px; font-size: {_fs('fs_12')}; font-weight: bold;"
        )
        self._start_ready_btn.clicked.connect(self._confirm_and_switch)
        self._start_ready_btn.hide()
        layout.addWidget(self._start_ready_btn)

        layout.addStretch()
        return page

    # ───────────────── Ready Page ─────────────────

    def _build_ready_page(self) -> QWidget:
        from .collapsible_section import CollapsibleSection
        p = current_palette()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header: image + controls ──
        header = QWidget(page)
        header.setStyleSheet(f"background: {p['bg_surface']}; border-bottom: 1px solid {p['line']};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(8))
        h_layout.setSpacing(_dp(10))

        # Compact drop zone
        self._drop_zone = _DropZone(self._t, header)
        self._drop_zone.setFixedSize(_dp(80), _dp(64))
        self._drop_zone.image_selected.connect(self._on_image_selected)
        h_layout.addWidget(self._drop_zone)

        # Right side: category toggles + model path
        right_col = QVBoxLayout()
        right_col.setSpacing(_dp(6))

        # Category toggles (always visible, primary control)
        from ..tagger import CATEGORY_NAMES
        cat_row = QHBoxLayout()
        cat_row.setSpacing(_dp(3))
        self._cat_buttons: dict[str, QPushButton] = {}
        for cat in CATEGORY_NAMES:
            btn = QPushButton(cat, header)
            btn.setCheckable(True)
            btn.setChecked(cat in self._enabled_categories)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_dp(20))
            btn.clicked.connect(partial(self._toggle_category, cat))
            self._cat_buttons[cat] = btn
            cat_row.addWidget(btn)
        cat_row.addStretch()
        right_col.addLayout(cat_row)
        self._apply_cat_styles()

        # Threshold inline (compact, no collapsible)
        thresh_row = QHBoxLayout()
        thresh_row.setSpacing(_dp(4))
        gl = QLabel(self._t.t("interr_general"), header)
        gl.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        gl.setToolTip(self._t.t("interr_general_tip"))
        thresh_row.addWidget(gl)
        self._gen_slider = QSlider(Qt.Orientation.Horizontal, header)
        self._gen_slider.setRange(5, 95)
        self._gen_slider.setValue(35)
        self._gen_slider.setFixedHeight(_dp(14))
        thresh_row.addWidget(self._gen_slider, 1)
        self._gen_value = QLabel("0.35", header)
        self._gen_value.setFixedWidth(_dp(26))
        self._gen_value.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; font-family: monospace;")
        self._gen_slider.valueChanged.connect(lambda v: self._gen_value.setText(f"{v/100:.2f}"))
        thresh_row.addWidget(self._gen_value)
        thresh_row.addSpacing(_dp(6))
        cl = QLabel(self._t.t("interr_character_label"), header)
        cl.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        cl.setToolTip(self._t.t("interr_character_tip"))
        thresh_row.addWidget(cl)
        self._char_slider = QSlider(Qt.Orientation.Horizontal, header)
        self._char_slider.setRange(5, 95)
        self._char_slider.setValue(70)
        self._char_slider.setFixedHeight(_dp(14))
        thresh_row.addWidget(self._char_slider, 1)
        self._char_value = QLabel("0.70", header)
        self._char_value.setFixedWidth(_dp(26))
        self._char_value.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; font-family: monospace;")
        self._char_slider.valueChanged.connect(lambda v: self._char_value.setText(f"{v/100:.2f}"))
        thresh_row.addWidget(self._char_value)
        right_col.addLayout(thresh_row)

        # Model path
        path_row = QHBoxLayout()
        path_row.setSpacing(_dp(4))
        self._path_display = QLabel("", header)
        self._path_display.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        path_row.addWidget(self._path_display, 1)
        browse_btn = QPushButton("📂", header)
        browse_btn.setFixedSize(_dp(16), _dp(16))
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setToolTip(self._t.t("interr_browse_dir_tip"))
        browse_btn.setStyleSheet(f"border: none; background: transparent; font-size: {_fs('fs_9')};")
        browse_btn.clicked.connect(self._browse_model_dir)
        path_row.addWidget(browse_btn)
        right_col.addLayout(path_row)

        h_layout.addLayout(right_col, 1)
        layout.addWidget(header)

        # ── Body ──
        body = QWidget(page)
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(_dp(10), _dp(6), _dp(10), _dp(8))
        b_layout.setSpacing(_dp(4))

        # Status bar
        status_row = QHBoxLayout()
        status_row.setSpacing(_dp(6))
        self._status = QLabel("", body)
        self._status.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        status_row.addWidget(self._status, 1)
        self._show_conf = True
        self._conf_btn = QPushButton(self._t.t("interr_hide_conf"), body)
        self._conf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._conf_btn.setFixedHeight(_dp(18))
        self._conf_btn.setStyleSheet(
            f"background: transparent; color: {p['text_dim']}; "
            f"border: 1px solid {p['line']}; border-radius: 3px; "
            f"padding: 0 6px; font-size: {_fs('fs_9')};"
        )
        self._conf_btn.clicked.connect(self._toggle_confidence)
        status_row.addWidget(self._conf_btn)
        b_layout.addLayout(status_row)

        # Result text
        self._result_edit = QTextEdit(body)
        self._result_edit.setReadOnly(True)
        self._result_edit.setStyleSheet(
            f"background: {p['bg_input']}; color: {p['text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 8px; font-size: {_fs('fs_10')};"
        )
        b_layout.addWidget(self._result_edit, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(_dp(8))
        btn_row.addStretch()
        copy_btn = QPushButton(self._t.t("copy"), body)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(
            f"background: transparent; color: {p['text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 4px 16px; font-size: {_fs('fs_10')};"
        )
        copy_btn.clicked.connect(self._copy_result)
        btn_row.addWidget(copy_btn)
        send_btn = QPushButton(self._t.t("interrogator_send_to_input"), body)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 4px 16px; font-size: {_fs('fs_10')};"
        )
        send_btn.clicked.connect(self._send_result)
        btn_row.addWidget(send_btn)
        b_layout.addLayout(btn_row)

        layout.addWidget(body, 1)
        return page

    # ───────────────── Install ─────────────────

    def _install_deps(self, btn: QPushButton):
        btn.setText(self._t.t("interr_installing"))
        btn.setEnabled(False)
        self._setup_status.setText("")
        import subprocess, sys

        class _InstallWorker(QThread):
            finished = pyqtSignal(bool, str)
            def run(wself):
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", "onnxruntime", "numpy", "Pillow"],
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                    )
                    wself.finished.emit(True, "")
                except Exception as e:
                    wself.finished.emit(False, str(e))

        def _on_done(ok, err):
            if ok:
                btn.setText(self._t.t("interr_install_done"))
                btn.setEnabled(False)
                self._setup_status.setText(self._t.t("interr_deps_installed"))
                restart_btn = QPushButton(self._t.t("interr_restart"), self)
                restart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                p = current_palette()
                restart_btn.setStyleSheet(
                    f"background: {p['accent']}; color: {p['accent_text']}; "
                    f"border: none; border-radius: 4px; padding: 8px 20px; "
                    f"font-size: {_fs('fs_11')}; font-weight: bold;"
                )
                restart_btn.clicked.connect(self._restart_app)
                # Insert after status label
                idx = self._setup_page.layout().indexOf(self._setup_status)
                self._setup_page.layout().insertWidget(idx + 1, restart_btn)
            else:
                btn.setText(self._t.t("interr_install_deps"))
                btn.setEnabled(True)
                self._setup_status.setText(self._t.t("interr_install_failed").format(error=err))

        self._install_worker = _InstallWorker(self)
        self._install_worker.finished.connect(_on_done)
        self._install_worker.start()

    def _prompt_python_setup(self, model_dir: str):
        """Show setup options when onnxruntime can't load directly."""
        self._pending_model_dir = model_dir
        self._stack.setCurrentIndex(0)
        self._update_setup_status()

    def _browse_python(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._t.t("interr_select_python"), "",
            "Python (python.exe python3.exe);;All (*)"
        )
        if not path:
            return
        self._external_python = path
        self.python_path_changed.emit(path)
        if self._engine:
            self._engine.set_external_python(path)
            if self._engine._model_path:
                self._engine.load(
                    self._engine._model_path, self._engine._mapping_path,
                    external_python=path,
                )
        self._update_setup_status()

    # ───────────────── Auto Setup ─────────────────

    def _start_env_setup(self):
        """Start downloading and setting up embedded Python environment."""
        from ..python_env import PythonEnvSetupWorker
        if hasattr(self, '_auto_setup_btn'):
            self._auto_setup_btn.setEnabled(False)
            self._auto_setup_btn.setText(self._t.t("interr_configuring"))
        self._setup_progress.show()
        self._setup_progress.setValue(0)
        self._setup_status.setText("")

        self._env_worker = PythonEnvSetupWorker(self)
        self._env_worker.progress.connect(self._on_env_setup_progress)
        self._env_worker.finished.connect(self._on_env_setup_done)
        self._env_worker.error.connect(self._on_env_setup_error)
        self._env_worker.start()

    def _on_env_setup_progress(self, message: str, percent: int):
        self._setup_status.setText(message)
        self._setup_progress.setValue(percent)

    def _on_env_setup_done(self, python_path: str):
        self._setup_progress.setValue(100)
        self._external_python = python_path
        self.python_path_changed.emit(python_path)
        if self._engine:
            self._engine.set_external_python(python_path)

        # Re-load model with new python if model was already found
        if self._engine and self._engine._model_path:
            self._engine.load(
                self._engine._model_path, self._engine._mapping_path,
                external_python=python_path,
            )
        if hasattr(self, '_auto_setup_btn'):
            self._auto_setup_btn.setText(self._t.t("interr_configured"))
        self._update_setup_status()

    def _on_env_setup_error(self, error: str):
        self._setup_progress.hide()
        self._setup_status.setText(self._t.t("interr_config_failed").format(error=error))
        if hasattr(self, '_auto_setup_btn'):
            self._auto_setup_btn.setEnabled(True)
            self._auto_setup_btn.setText(self._t.t("interr_auto_setup"))

    def _restart_app(self):
        """Restart the application."""
        import subprocess as _sp
        if getattr(sys, '_MEIPASS', None):
            # Packaged exe — just re-run the exe
            _sp.Popen([sys.executable])
        else:
            # Source mode — python -m native_app
            _sp.Popen([sys.executable, "-m", "native_app"],
                      cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        QApplication.quit()

    # ───────────────── Engine ─────────────────

    def _try_auto_load(self):
        try:
            from ..tagger import TaggerEngine
            from ..python_env import get_embedded_python_path, is_env_usable
            self._engine = TaggerEngine()
            appdata = os.environ.get("APPDATA", "")
            appdata_dir = os.path.join(appdata, "HainTag") if appdata else None

            # Try find_model first (exact filenames)
            model_path, mapping_path = self._engine.find_model(
                custom_dir=self._custom_model_dir or None,
                appdata_dir=appdata_dir,
            )

            # Fallback: scan custom_model_dir for any .onnx + mapping json
            if not model_path and self._custom_model_dir and os.path.isdir(self._custom_model_dir):
                model_path, mapping_path = self._scan_model_dir(self._custom_model_dir)

            if not model_path:
                self._stack.setCurrentIndex(0)
                return

            # Resolve external python: saved path > embedded env > None
            ext_python = self._external_python or None
            if not ext_python:
                embedded = get_embedded_python_path()
                if embedded and is_env_usable(embedded):
                    ext_python = embedded
                    self._external_python = embedded
                    self.python_path_changed.emit(embedded)

            self._engine.load(model_path, mapping_path, external_python=ext_python)
            # Startup: auto-switch only if fully ready
            if self._can_infer():
                self._switch_to_ready(os.path.dirname(model_path))
            else:
                self._stack.setCurrentIndex(0)
                self._update_setup_status()
        except Exception:
            self._stack.setCurrentIndex(0)

    @staticmethod
    def _scan_model_dir(path: str) -> tuple[str | None, str | None]:
        """Scan directory for any .onnx model + tag mapping json."""
        model_file = mapping_file = None
        for f in os.listdir(path):
            fl = f.lower()
            if fl.endswith(".onnx") and not model_file:
                model_file = os.path.join(path, f)
            elif fl.endswith(".json") and ("tag" in fl or "mapping" in fl) and not mapping_file:
                mapping_file = os.path.join(path, f)
        if model_file and mapping_file:
            return model_file, mapping_file
        return None, None

    def _rebuild_pages(self):
        """Rebuild both pages to pick up new theme/font settings."""
        current = self._stack.currentIndex()
        # Remove old pages
        old_setup = self._stack.widget(0)
        old_ready = self._stack.widget(1)
        self._stack.removeWidget(old_setup)
        self._stack.removeWidget(old_ready)
        old_setup.deleteLater()
        old_ready.deleteLater()
        # Rebuild
        self._setup_page = self._build_setup_page()
        self._stack.insertWidget(0, self._setup_page)
        ready_page = self._build_ready_page()
        self._stack.insertWidget(1, ready_page)
        self._stack.setCurrentIndex(current)
        # Re-apply category styles
        self._apply_cat_styles()
        # Re-render results if any
        self._render_results()

    def _switch_to_ready(self, model_dir: str):
        self._stack.setCurrentIndex(1)
        self._path_display.setText(model_dir)
        self._status.setText(self._t.t("interr_model_loaded"))

    def _confirm_and_switch(self):
        """User clicked 'Start' — switch to ready page if everything is set."""
        if self._can_infer():
            model_dir = os.path.dirname(self._engine._model_path)
            self._switch_to_ready(model_dir)
            self.model_dir_changed.emit(model_dir)
        else:
            self._update_setup_status()

    def _can_infer(self) -> bool:
        """Check if engine is fully ready to run inference."""
        if not self._engine or not self._engine.is_ready:
            return False
        if self._engine._use_subprocess and not self._engine._external_python:
            return False
        return True

    def _update_setup_status(self):
        """Update setup page status text based on current state. Never auto-switches."""
        parts = []
        if self._engine and self._engine._model_path:
            parts.append(self._t.t("interr_model_loaded"))
        else:
            parts.append(self._t.t("interr_please_select_dir"))

        if self._engine and not self._engine._use_subprocess:
            parts.append(self._t.t("interr_onnx_available"))
        elif self._external_python:
            parts.append(self._t.t("interr_python_configured"))
        else:
            parts.append(self._t.t("interr_please_config_python"))

        self._setup_status.setText("\n".join(parts))

        # Show/hide the start button
        if hasattr(self, '_start_ready_btn'):
            self._start_ready_btn.setVisible(self._can_infer())

    def _browse_model_dir(self):
        path = QFileDialog.getExistingDirectory(self, self._t.t("interr_select_model_dir_dialog"))
        if not path:
            return
        self._custom_model_dir = path
        model_file, mapping_file = self._scan_model_dir(path)
        if model_file and mapping_file:
            try:
                from ..tagger import TaggerEngine
                if self._engine is None:
                    self._engine = TaggerEngine()
                self._engine.load(model_file, mapping_file,
                                  external_python=self._external_python or None)
                self.model_dir_changed.emit(path)
                self._update_setup_status()
            except Exception as e:
                self._setup_status.setText(self._t.t("interr_load_failed").format(error=e))
        else:
            self._setup_status.setText(self._t.t("interr_no_model_found"))

    # ───────────────── Inference ─────────────────

    def _toggle_category(self, cat: str):
        if cat in self._enabled_categories:
            self._enabled_categories.discard(cat)
        else:
            self._enabled_categories.add(cat)
        self._apply_cat_styles()

    def _apply_cat_styles(self):
        p = current_palette()
        for cat, btn in self._cat_buttons.items():
            if cat in self._enabled_categories:
                btn.setStyleSheet(
                    f"background: {p['accent']}; color: {p['accent_text']}; "
                    f"border: none; border-radius: 3px; padding: 1px 5px; font-size: {_fs('fs_9')};"
                )
            else:
                btn.setStyleSheet(
                    f"background: transparent; color: {p['text_dim']}; "
                    f"border: 1px solid {p['line']}; border-radius: 3px; padding: 1px 5px; font-size: {_fs('fs_9')};"
                )

    def _on_image_selected(self, path: str):
        self._image_path = path
        if self._engine and self._engine.is_ready:
            self._run_inference()

    def _run_inference(self):
        if not self._image_path or not self._engine or not self._engine.is_ready:
            return
        from ..tagger import TaggerWorker
        self._status.setText(self._t.t("interr_inferring"))
        self._result_edit.clear()
        self._worker = TaggerWorker(
            self._engine, self._image_path,
            self._gen_slider.value() / 100.0,
            self._char_slider.value() / 100.0,
            set(self._enabled_categories), list(self._blacklist), self,
        )
        self._worker.finished.connect(self._on_inference_done)
        self._worker.error.connect(self._on_inference_error)
        self._worker.start()

    def _on_inference_error(self, error: str):
        self._status.setText(self._t.t("interr_infer_failed"))
        self._result_edit.setPlainText(error)
        if not hasattr(self, '_back_to_setup_btn') or not self._back_to_setup_btn.isVisible():
            p = current_palette()
            self._back_to_setup_btn = QPushButton(self._t.t("interr_back_to_setup"), self._result_edit.parent())
            self._back_to_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._back_to_setup_btn.setStyleSheet(
                f"background: transparent; color: {p['accent_text']}; "
                f"border: 1px solid {p['line']}; border-radius: 4px; "
                f"padding: 4px 12px; font-size: {_fs('fs_10')};"
            )
            self._back_to_setup_btn.clicked.connect(lambda: (
                self._stack.setCurrentIndex(0),
                self._update_setup_status(),
                self._back_to_setup_btn.hide(),
            ))
            # Insert after status label
            body_layout = self._status.parent().layout()
            status_idx = body_layout.indexOf(self._status)
            body_layout.insertWidget(status_idx + 1, self._back_to_setup_btn)

    def _on_inference_done(self, results: dict):
        self._last_results = results
        total = sum(len(v) for v in results.values())
        self._status.setText(f"✓ {total} tags")
        self._render_results()

    def _render_results(self):
        """Render results with or without confidence scores."""
        results = getattr(self, '_last_results', None)
        if not results:
            return
        lines = []
        all_tags = []
        for category, entries in results.items():
            if self._show_conf:
                tag_strs = [f"{name} ({prob:.0%})" for name, prob in entries]
            else:
                tag_strs = [name for name, _ in entries]
            lines.append(f"── {category} ({len(entries)}) ──")
            lines.append(", ".join(tag_strs))
            lines.append("")
            all_tags.extend(name for name, _ in entries)
        self._result_edit.setPlainText("\n".join(lines).rstrip())
        self._all_tags_str = ", ".join(all_tags)

    def _toggle_confidence(self):
        self._show_conf = not self._show_conf
        p = current_palette()
        if self._show_conf:
            self._conf_btn.setText(self._t.t("interr_hide_conf"))
            self._conf_btn.setStyleSheet(
                f"background: transparent; color: {p['text_dim']}; "
                f"border: 1px solid {p['line']}; border-radius: 3px; "
                f"padding: 0 6px; font-size: {_fs('fs_9')};"
            )
        else:
            self._conf_btn.setText(self._t.t("interr_show_conf"))
            self._conf_btn.setStyleSheet(
                f"background: transparent; color: {p['text_dim']}; "
                f"border: 1px solid {p['line']}; border-radius: 3px; "
                f"padding: 0 6px; font-size: {_fs('fs_9')};"
            )
        self._render_results()

    def _copy_result(self):
        QApplication.clipboard().setText(self._all_tags_str or self._result_edit.toPlainText())

    def _send_result(self):
        text = self._all_tags_str or self._result_edit.toPlainText()
        if text:
            self.send_to_input.emit(text)


# ═══════════════════════════════════════════════════
#  Flow Layout (for tag display)
# ═══════════════════════════════════════════════════

from PyQt6.QtCore import QRect, QSize


class _FlowLayout(QLayout):
    """Simple flow layout that wraps widgets like text words."""

    def __init__(self, parent=None, spacing: int = 4):
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        sp = self._spacing

        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            if x + w > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + sp
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, w, h))
            x += w + sp
            line_height = max(line_height, h)

        return y + line_height - rect.y()


# ═══════════════════════════════════════════════════
#  LLM Vision Tab
# ═══════════════════════════════════════════════════

class _LLMTaggerTab(QWidget):
    """Tab for LLM multimodal image tagging with batch, presets, and tag validation."""

    send_to_input = pyqtSignal(str)
    settings_changed = pyqtSignal()

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self._t = translator
        self._tag_dict = None
        self._image_paths: list[str] = []
        self._results: list = []
        self._current_index: int = 0
        self._worker = None
        self._raw_buffer: str = ""
        self._presets: list[dict] = []
        self._populating: bool = False

        self._api_base_url = ""
        self._api_key = ""
        self._model = ""

        self._build_ui()

    def _build_ui(self):
        from .collapsible_section import CollapsibleSection
        from .common import ToggleSwitch

        root = QVBoxLayout(self)
        root.setContentsMargins(_dp(10), _dp(10), _dp(10), _dp(10))
        root.setSpacing(_dp(12))

        # ── Drop zone ──
        self._drop_zone = _DropZone(self._t, self, multi=True)
        self._drop_zone.image_selected.connect(lambda path: self._on_images_selected([path]))
        self._drop_zone.images_selected.connect(self._on_images_selected)
        root.addWidget(self._drop_zone)

        # ── Action strip (elevated bar) ──
        self._action_strip = QWidget(self)
        self._action_strip.setObjectName('LLMActionStrip')
        strip_layout = QVBoxLayout(self._action_strip)
        strip_layout.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(8))
        strip_layout.setSpacing(_dp(6))

        action_row = QHBoxLayout()
        action_row.setSpacing(_dp(8))

        self._preset_combo = QComboBox(self._action_strip)
        self._preset_combo.setProperty('class', 'FieldCombo')
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        action_row.addWidget(self._preset_combo, 1)

        self._start_btn = QPushButton(self._t.t("interrogator_start"), self._action_strip)
        self._start_btn.setObjectName('PrimaryButton')
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._start_batch)
        action_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton(self._t.t("llm_tagger_stop"), self._action_strip)
        self._stop_btn.setObjectName('SecondaryButton')
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self._stop_batch)
        self._stop_btn.hide()
        action_row.addWidget(self._stop_btn)

        strip_layout.addLayout(action_row)

        self._status = QLabel("", self._action_strip)
        strip_layout.addWidget(self._status)

        root.addWidget(self._action_strip)

        # ── Results panel (inset container) ──
        self._results_panel = QWidget(self)
        self._results_panel.setObjectName('LLMResultsPanel')
        rp_layout = QVBoxLayout(self._results_panel)
        rp_layout.setContentsMargins(_dp(1), _dp(1), _dp(1), _dp(1))
        rp_layout.setSpacing(0)

        self._scroll = QScrollArea(self._results_panel)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(_dp(4), _dp(4), _dp(4), _dp(4))
        self._results_layout.setSpacing(_dp(4))
        self._results_layout.addStretch()
        self._scroll.setWidget(self._results_container)
        rp_layout.addWidget(self._scroll, 1)

        self._btn_sep = QFrame(self._results_panel)
        self._btn_sep.setFrameShape(QFrame.Shape.HLine)
        self._btn_sep.setFixedHeight(1)
        rp_layout.addWidget(self._btn_sep)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(_dp(8), _dp(6), _dp(8), _dp(6))
        bottom_row.addStretch()
        self._copy_all_btn = QPushButton(self._t.t("llm_tagger_copy_all"), self._results_panel)
        self._copy_all_btn.setObjectName('SecondaryButton')
        self._copy_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_all_btn.clicked.connect(self._copy_all)
        bottom_row.addWidget(self._copy_all_btn)
        self._send_all_btn = QPushButton(self._t.t("llm_tagger_send_all"), self._results_panel)
        self._send_all_btn.setObjectName('SecondaryButton')
        self._send_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_all_btn.clicked.connect(self._send_all)
        bottom_row.addWidget(self._send_all_btn)
        rp_layout.addLayout(bottom_row)

        root.addWidget(self._results_panel, 1)

        # ── Edit section (collapsed by default) ──
        edit_content = QWidget(self)
        edit_layout = QVBoxLayout(edit_content)
        edit_layout.setContentsMargins(0, _dp(4), 0, 0)
        edit_layout.setSpacing(_dp(6))

        edit_row = QHBoxLayout()
        edit_row.setSpacing(_dp(6))
        self._name_edit = QLineEdit(self)
        self._name_edit.setProperty('class', 'FieldInput')
        self._name_edit.setPlaceholderText(self._t.t("llm_tagger_preset_name"))
        self._name_edit.textChanged.connect(self._on_name_edited)
        edit_row.addWidget(self._name_edit, 1)

        self._add_preset_btn = QPushButton("+", self)
        self._add_preset_btn.setObjectName('PrimaryIconButton')
        self._add_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_preset_btn.clicked.connect(self._add_preset)
        edit_row.addWidget(self._add_preset_btn)

        self._del_preset_btn = QPushButton("×", self)
        self._del_preset_btn.setObjectName('SecondaryIconButton')
        self._del_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_preset_btn.clicked.connect(self._delete_preset)
        edit_row.addWidget(self._del_preset_btn)

        edit_layout.addLayout(edit_row)

        self._prompt_edit = QTextEdit(self)
        self._prompt_edit.setMaximumHeight(_dp(120))
        self._prompt_edit.setProperty('class', 'FieldInput')
        self._prompt_edit.setPlaceholderText(self._t.t("interrogator_llm_prompt"))
        self._prompt_edit.textChanged.connect(self._on_text_edited)
        edit_layout.addWidget(self._prompt_edit)

        api_row = QHBoxLayout()
        api_row.setSpacing(_dp(6))
        self._api_toggle_label = QLabel(self._t.t("llm_tagger_use_separate_api"), self)
        self._api_toggle_label.setProperty('class', 'FieldLabel')
        api_row.addWidget(self._api_toggle_label)
        api_row.addStretch()
        self._api_toggle = ToggleSwitch(self)
        self._api_toggle.toggled.connect(self._on_api_toggle)
        api_row.addWidget(self._api_toggle)
        edit_layout.addLayout(api_row)

        self._api_fields_widget = QWidget(self)
        api_fields = QVBoxLayout(self._api_fields_widget)
        api_fields.setContentsMargins(0, 0, 0, 0)
        api_fields.setSpacing(_dp(4))

        self._separate_url = QLineEdit(self)
        self._separate_url.setProperty('class', 'FieldInput')
        self._separate_url.setPlaceholderText(self._t.t("llm_tagger_api_base_url"))
        self._separate_url.textChanged.connect(self._on_api_field_changed)
        api_fields.addWidget(self._separate_url)

        self._separate_key = QLineEdit(self)
        self._separate_key.setProperty('class', 'FieldInput')
        self._separate_key.setPlaceholderText(self._t.t("llm_tagger_api_key"))
        self._separate_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._separate_key.textChanged.connect(self._on_api_field_changed)
        api_fields.addWidget(self._separate_key)

        self._separate_model = QLineEdit(self)
        self._separate_model.setProperty('class', 'FieldInput')
        self._separate_model.setPlaceholderText(self._t.t("llm_tagger_api_model"))
        self._separate_model.textChanged.connect(self._on_api_field_changed)
        api_fields.addWidget(self._separate_model)

        self._api_fields_widget.hide()
        edit_layout.addWidget(self._api_fields_widget)

        self._edit_section = CollapsibleSection(
            self._t.t("llm_tagger_edit_section"), edit_content,
            collapsed=True, parent=self,
        )
        root.addWidget(self._edit_section)

    # ── Public API ──

    def set_api_settings(self, base_url: str, api_key: str, model: str):
        self._api_base_url = base_url
        self._api_key = api_key
        self._model = model

    def set_tag_dictionary(self, dictionary):
        self._tag_dict = dictionary

    def apply_llm_settings(self, settings):
        self._populating = True
        self._presets = [dict(p) for p in (settings.tagger_llm_presets or [])]
        self._preset_combo.clear()
        for p in self._presets:
            self._preset_combo.addItem(p.get("name", ""))
        idx = min(settings.tagger_llm_active_preset, len(self._presets) - 1) if self._presets else -1
        self._preset_combo.setCurrentIndex(idx)
        self._sync_fields_to_preset(idx)
        self._api_toggle.setChecked(settings.tagger_llm_use_separate)
        self._api_fields_widget.setVisible(settings.tagger_llm_use_separate)
        if settings.tagger_llm_base_url:
            self._separate_url.setText(settings.tagger_llm_base_url)
        if settings.tagger_llm_api_key:
            self._separate_key.setText(settings.tagger_llm_api_key)
        if settings.tagger_llm_model:
            self._separate_model.setText(settings.tagger_llm_model)
        self._populating = False

    def collect_llm_settings(self) -> dict:
        return {
            "tagger_llm_presets": [dict(p) for p in self._presets],
            "tagger_llm_active_preset": max(0, self._preset_combo.currentIndex()),
            "tagger_llm_use_separate": self._api_toggle.isChecked(),
            "tagger_llm_base_url": self._separate_url.text(),
            "tagger_llm_api_key": self._separate_key.text(),
            "tagger_llm_model": self._separate_model.text(),
        }

    # ── Slots ──

    def _on_images_selected(self, paths: list[str]):
        self._image_paths = paths

    def _on_preset_selected(self, index: int):
        if self._populating:
            return
        self._populating = True
        self._sync_fields_to_preset(index)
        self._populating = False
        self.settings_changed.emit()

    def _sync_fields_to_preset(self, index: int):
        if 0 <= index < len(self._presets):
            self._name_edit.setText(self._presets[index].get("name", ""))
            self._prompt_edit.setPlainText(self._presets[index].get("text", ""))
            self._name_edit.setEnabled(True)
            self._prompt_edit.setEnabled(True)
        else:
            self._name_edit.clear()
            self._prompt_edit.clear()
            self._name_edit.setEnabled(len(self._presets) == 0)
            self._prompt_edit.setEnabled(True)

    def _on_name_edited(self, text: str):
        if self._populating:
            return
        idx = self._preset_combo.currentIndex()
        if 0 <= idx < len(self._presets):
            self._presets[idx]["name"] = text
            self._preset_combo.setItemText(idx, text)
            self.settings_changed.emit()

    def _on_text_edited(self):
        if self._populating:
            return
        idx = self._preset_combo.currentIndex()
        if 0 <= idx < len(self._presets):
            self._presets[idx]["text"] = self._prompt_edit.toPlainText()
            self.settings_changed.emit()

    def _add_preset(self):
        name = self._t.t("llm_tagger_new_preset") + f" {len(self._presets) + 1}"
        self._presets.append({"name": name, "text": ""})
        self._populating = True
        self._preset_combo.addItem(name)
        self._preset_combo.setCurrentIndex(len(self._presets) - 1)
        self._sync_fields_to_preset(len(self._presets) - 1)
        self._populating = False
        self._name_edit.setFocus()
        self._name_edit.selectAll()
        self.settings_changed.emit()

    def _delete_preset(self):
        idx = self._preset_combo.currentIndex()
        if idx < 0 or idx >= len(self._presets):
            return
        self._populating = True
        self._presets.pop(idx)
        self._preset_combo.removeItem(idx)
        new_idx = min(idx, len(self._presets) - 1) if self._presets else -1
        self._preset_combo.setCurrentIndex(new_idx)
        self._sync_fields_to_preset(new_idx)
        self._populating = False
        self.settings_changed.emit()

    def _on_api_field_changed(self):
        if self._populating:
            return
        self.settings_changed.emit()

    def _on_api_toggle(self, checked: bool):
        self._api_fields_widget.setVisible(checked)
        if not self._populating:
            self.settings_changed.emit()

    def _get_effective_api(self) -> tuple[str, str, str]:
        if self._api_toggle.isChecked() and self._separate_url.text().strip():
            return (
                self._separate_url.text().strip(),
                self._separate_key.text().strip(),
                self._separate_model.text().strip(),
            )
        return (self._api_base_url, self._api_key, self._model)

    def _get_prompt_text(self) -> str:
        idx = self._preset_combo.currentIndex()
        if 0 <= idx < len(self._presets):
            return self._presets[idx].get("text", "").strip()
        return self._prompt_edit.toPlainText().strip()

    # ── Batch processing ──

    def _start_batch(self):
        if not self._image_paths:
            self._status.setText(self._t.t("interrogator_no_image"))
            return
        base_url, api_key, model = self._get_effective_api()
        if not base_url or not api_key or not model:
            self._status.setText(self._t.t("llm_tagger_no_api"))
            return

        self._results.clear()
        self._current_index = 0
        self._start_btn.setEnabled(False)
        self._stop_btn.show()
        self._clear_result_widgets()
        self._process_next()

    def _process_next(self):
        if self._current_index >= len(self._image_paths):
            self._on_batch_finished()
            return

        path = self._image_paths[self._current_index]
        self._status.setText(
            self._t.t("llm_tagger_batch_progress")
            .replace("{current}", str(self._current_index + 1))
            .replace("{total}", str(len(self._image_paths)))
        )
        self._raw_buffer = ""

        from ..llm_tagger_logic import build_vision_messages
        from ..api_client import ChatWorker
        from ..logic import normalize_api_base_url

        base_url, api_key, model = self._get_effective_api()
        messages = build_vision_messages(path, self._get_prompt_text())
        url = f"{normalize_api_base_url(base_url)}/chat/completions"
        payload = {"model": model, "messages": messages, "max_tokens": 4096, "stream": True}

        self._worker = ChatWorker(url, payload, api_key, stream=True, summary_mode=False)
        self._worker.delta_received.connect(self._on_delta)
        self._worker.error_received.connect(self._on_error)
        self._worker.finished_cleanly.connect(self._on_single_finished)
        self._worker.start()

    def _on_delta(self, text: str):
        self._raw_buffer += text

    def _on_single_finished(self):
        from ..llm_tagger_logic import parse_llm_tags, validate_tags
        from ..models import LLMTagResult

        path = self._image_paths[self._current_index]
        tags = parse_llm_tags(self._raw_buffer)
        parsed = validate_tags(tags, self._tag_dict)

        result = LLMTagResult(image_path=path, raw_text=self._raw_buffer, parsed_tags=parsed)
        self._results.append(result)
        self._add_result_widget(result)

        self._current_index += 1
        self._process_next()

    def _on_error(self, message: str, status_code: int, details: str):
        from ..models import LLMTagResult

        path = self._image_paths[self._current_index]
        result = LLMTagResult(image_path=path, raw_text=f"[Error] {message}")
        self._results.append(result)
        self._add_result_widget(result)

        self._current_index += 1
        self._process_next()

    def _stop_batch(self):
        if self._worker:
            self._worker.cancel()
        self._current_index = len(self._image_paths)
        self._on_batch_finished()

    def _on_batch_finished(self):
        self._start_btn.setEnabled(True)
        self._stop_btn.hide()
        total_valid = sum(1 for r in self._results for t in r.parsed_tags if t.is_valid)
        self._status.setText(
            self._t.t("llm_tagger_valid_tags").replace("{count}", str(total_valid))
        )

    # ── Result display ──

    def _clear_result_widgets(self):
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_result_widget(self, result):
        from .collapsible_section import CollapsibleSection
        from .tag_completer import _CATEGORY_COLORS

        p = current_palette()
        content = QWidget()
        flow = _FlowLayout(content, spacing=_dp(4))

        for ptag in result.parsed_tags:
            label = QLabel(ptag.name.replace("_", " "))
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            if ptag.is_valid:
                dark_c, light_c = _CATEGORY_COLORS.get(ptag.category_id, ("#6699FF", "#0055CC"))
                color = light_c if is_theme_light() else dark_c
                label.setStyleSheet(
                    f"color: {color}; background: transparent; "
                    f"padding: 2px 6px; font-size: {_fs('fs_10')};"
                )
                if ptag.translation:
                    label.setToolTip(ptag.translation)
            else:
                label.setStyleSheet(
                    f"color: {p['text_dim']}; background: transparent; "
                    f"padding: 2px 6px; font-size: {_fs('fs_10')}; "
                    f"font-style: italic;"
                )
                label.setToolTip(self._t.t("llm_tagger_unknown_tag"))
            flow.addWidget(label)

        if result.raw_text.startswith("[Error]"):
            err_label = QLabel(result.raw_text)
            err_label.setStyleSheet(f"color: {p['accent_warn']}; font-size: {_fs('fs_9')};")
            err_label.setWordWrap(True)
            flow.addWidget(err_label)

        title = os.path.basename(result.image_path)
        section = CollapsibleSection(title, content, collapsed=False, parent=self._results_container)
        insert_pos = self._results_layout.count() - 1
        self._results_layout.insertWidget(insert_pos, section)

    # ── Copy / Send ──

    def _collect_all_tags(self) -> str:
        seen: set[str] = set()
        tags: list[str] = []
        for r in self._results:
            for t in r.parsed_tags:
                if t.name not in seen:
                    seen.add(t.name)
                    tags.append(t.name)
        return ", ".join(tags)

    def _copy_all(self):
        text = self._collect_all_tags()
        if text:
            QApplication.clipboard().setText(text)

    def _send_all(self):
        text = self._collect_all_tags()
        if text:
            self.send_to_input.emit(text)

    # ── Theme / i18n ──

    def apply_theme(self):
        p = current_palette()
        # Action strip: elevated bar (scoped to avoid child inheritance)
        self._action_strip.setStyleSheet(
            f"QWidget#LLMActionStrip {{ background: {p['bg_surface']}; "
            f"border: 1px solid {p['line']}; border-radius: 6px; }}"
        )
        self._status.setStyleSheet(
            f"color: {p['text_muted']}; font-size: {_fs('fs_9')};"
        )
        # Results panel: inset container (scoped)
        self._results_panel.setStyleSheet(
            f"QWidget#LLMResultsPanel {{ background: {p['bg_input']}; "
            f"border: 1px solid {p['line']}; border-radius: 6px; }}"
        )
        self._btn_sep.setStyleSheet(f"background: {p['line']}; border: none;")
        # Drop zone
        self._drop_zone.apply_theme()
        # Edit section: de-emphasize
        self._edit_section.apply_theme()
        self._edit_section._toggle_btn.setStyleSheet(
            f"color: {p['text_muted']}; border: none; font-size: {_fs('fs_10')};"
        )
        self._edit_section._title_label.setStyleSheet(
            f"color: {p['text_muted']}; font-size: {_fs('fs_12')};"
        )

    def retranslate_ui(self):
        self._edit_section.set_title(self._t.t("llm_tagger_edit_section"))
        self._name_edit.setPlaceholderText(self._t.t("llm_tagger_preset_name"))
        self._prompt_edit.setPlaceholderText(self._t.t("interrogator_llm_prompt"))
        self._api_toggle_label.setText(self._t.t("llm_tagger_use_separate_api"))
        self._separate_url.setPlaceholderText(self._t.t("llm_tagger_api_base_url"))
        self._separate_key.setPlaceholderText(self._t.t("llm_tagger_api_key"))
        self._separate_model.setPlaceholderText(self._t.t("llm_tagger_api_model"))
        self._start_btn.setText(self._t.t("interrogator_start"))
        self._stop_btn.setText(self._t.t("llm_tagger_stop"))
        self._copy_all_btn.setText(self._t.t("llm_tagger_copy_all"))
        self._send_all_btn.setText(self._t.t("llm_tagger_send_all"))


# ═══════════════════════════════════════════════════
#  Drop Zone (shared)
# ═══════════════════════════════════════════════════

_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;All (*)"


class _DropZone(QFrame):
    """Image drop zone with preview. Supports single or multi-image mode."""

    image_selected = pyqtSignal(str)
    images_selected = pyqtSignal(list)

    def __init__(self, translator: Translator, parent=None, *, multi: bool = False):
        super().__init__(parent)
        self._t = translator
        self._multi = multi
        self.setAcceptDrops(True)
        self.setMinimumHeight(_dp(48))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint_key = "llm_tagger_drop_images" if multi else "interrogator_drop_image"
        self._label = QLabel(translator.t(hint_key), self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._preview = QLabel(self)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.hide()
        layout.addWidget(self._preview)

        self.apply_theme()

    def apply_theme(self):
        p = current_palette()
        self.setStyleSheet(
            f"background: {p['bg_input']}; border: 1px solid {p['line']}; border-radius: 6px;"
        )
        self._label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; border: none;")

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._multi:
            paths, _ = QFileDialog.getOpenFileNames(
                self, self._t.t("interrogator_select_image"), "", _IMAGE_FILTER
            )
            if paths:
                self._set_images(paths)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, self._t.t("interrogator_select_image"), "", _IMAGE_FILTER
            )
            if path:
                self._set_image(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        if self._multi:
            paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
            if paths:
                self._set_images(paths)
        else:
            path = urls[0].toLocalFile()
            if path:
                self._set_image(path)

    def _set_image(self, path: str):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        max_h = max(40, self.height() - 30)
        scaled = pixmap.scaled(max_h, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._preview.setPixmap(scaled)
        self._preview.show()
        self._label.setText(os.path.basename(path))
        self.image_selected.emit(path)

    def _set_images(self, paths: list[str]):
        valid: list[str] = []
        for p in paths:
            if not QPixmap(p).isNull():
                valid.append(p)
        if not valid:
            return
        if len(valid) == 1:
            self._set_image(valid[0])
            self.images_selected.emit(valid)
            return
        self._preview.hide()
        self._label.setText(
            self._t.t("llm_tagger_images_selected").replace("{count}", str(len(valid)))
        )
        self.images_selected.emit(valid)


# ═══════════════════════════════════════════════════
#  Main Widget
# ═══════════════════════════════════════════════════

class InterrogatorWidget(QWidget):
    """Image interrogator with local tagger and LLM vision tabs."""

    send_to_input = pyqtSignal(str)
    model_dir_changed = pyqtSignal(str)
    python_path_changed = pyqtSignal(str)

    def __init__(self, translator: Translator, parent=None,
                 model_dir: str = "", python_path: str = ""):
        super().__init__(parent)
        self._t = translator

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("OutputTabs")

        self._local_tab = _LocalTaggerTab(translator, self,
                                          model_dir=model_dir,
                                          python_path=python_path)
        self._local_tab.send_to_input.connect(self.send_to_input.emit)
        self._local_tab.model_dir_changed.connect(self.model_dir_changed.emit)
        self._local_tab.python_path_changed.connect(self.python_path_changed.emit)
        self._tabs.addTab(self._local_tab, translator.t("interrogator_local"))

        self._llm_tab = _LLMTaggerTab(translator, self)
        self._llm_tab.send_to_input.connect(self.send_to_input.emit)
        self._tabs.addTab(self._llm_tab, translator.t("interrogator_llm"))

        root.addWidget(self._tabs)

    def set_api_settings(self, base_url: str, api_key: str, model: str):
        self._llm_tab.set_api_settings(base_url, api_key, model)

    def set_tag_dictionary(self, dictionary):
        self._llm_tab.set_tag_dictionary(dictionary)

    def apply_llm_settings(self, settings):
        self._llm_tab.apply_llm_settings(settings)

    def collect_llm_settings(self) -> dict:
        return self._llm_tab.collect_llm_settings()

    def apply_theme(self):
        self._local_tab._rebuild_pages()
        self._llm_tab.apply_theme()

    def retranslate_ui(self):
        self._tabs.setTabText(0, self._t.t("interrogator_local"))
        self._tabs.setTabText(1, self._t.t("interrogator_llm"))
        self._llm_tab.retranslate_ui()
