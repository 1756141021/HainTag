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
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import Translator
from ..theme import _fs, current_palette


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
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(16)

        title = QLabel("本地 TAG 反推", page)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_14')}; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(
            "使用 cl_tagger 模型离线识别图片的 Danbooru 标签。\n"
            "首次使用需要下载模型文件（约 1.4GB）。",
            page,
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')};")
        layout.addWidget(desc)

        layout.addSpacing(8)

        steps = QLabel(
            "步骤：\n\n"
            "1. 前往 HuggingFace 下载以下两个文件：\n"
            "    • model_optimized.onnx（~1.4GB）\n"
            "    • tag_mapping.json（~4MB）\n\n"
            "2. 放在同一个文件夹中\n\n"
            "3. 点击下方「选择模型文件夹」\n\n"
            "如果已在 ComfyUI 等工具中下载过，直接选择那个目录即可。",
            page,
        )
        steps.setWordWrap(True)
        steps.setStyleSheet(
            f"color: {p['text']}; font-size: {_fs('fs_10')}; "
            f"background: {p['bg_surface']}; border: 1px solid {p['line']}; "
            f"border-radius: 6px; padding: 16px;"
        )
        layout.addWidget(steps)

        layout.addSpacing(8)

        # Buttons
        link_btn = QPushButton("打开下载页面", page)
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

        select_btn = QPushButton("选择模型文件夹", page)
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 8px 20px; font-size: {_fs('fs_11')}; font-weight: bold;"
        )
        select_btn.clicked.connect(self._browse_model_dir)
        layout.addWidget(select_btn)

        # Auto-setup button (always available)
        self._auto_setup_btn = QPushButton("自动配置 Python 环境 (~200MB)", page)
        self._auto_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auto_setup_btn.setStyleSheet(
            f"background: {p['accent']}; color: {p['accent_text']}; "
            f"border: none; border-radius: 4px; "
            f"padding: 8px 20px; font-size: {_fs('fs_10')}; font-weight: bold;"
        )
        self._auto_setup_btn.clicked.connect(self._start_env_setup)
        layout.addWidget(self._auto_setup_btn)

        # Manual Python path button (always available)
        manual_btn = QPushButton("手动选择 Python 路径", page)
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
        self._setup_progress.setFixedHeight(16)
        self._setup_progress.hide()
        layout.addWidget(self._setup_progress)

        self._setup_status = QLabel("", page)
        self._setup_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_status.setWordWrap(True)
        self._setup_status.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        layout.addWidget(self._setup_status)

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
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(10)

        # Compact drop zone
        self._drop_zone = _DropZone(self._t, header)
        self._drop_zone.setFixedSize(80, 64)
        self._drop_zone.image_selected.connect(self._on_image_selected)
        h_layout.addWidget(self._drop_zone)

        # Right side: category toggles + model path
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # Category toggles (always visible, primary control)
        from ..tagger import CATEGORY_NAMES
        cat_row = QHBoxLayout()
        cat_row.setSpacing(3)
        self._cat_buttons: dict[str, QPushButton] = {}
        for cat in CATEGORY_NAMES:
            btn = QPushButton(cat, header)
            btn.setCheckable(True)
            btn.setChecked(cat in self._enabled_categories)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(20)
            btn.clicked.connect(partial(self._toggle_category, cat))
            self._cat_buttons[cat] = btn
            cat_row.addWidget(btn)
        cat_row.addStretch()
        right_col.addLayout(cat_row)
        self._apply_cat_styles()

        # Threshold inline (compact, no collapsible)
        thresh_row = QHBoxLayout()
        thresh_row.setSpacing(4)
        gl = QLabel("通用", header)
        gl.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        gl.setToolTip("通用标签 (general) 的最低置信度阈值\n"
                       "例如：1girl, red_hair, smile 等描述画面的标签\n"
                       "值越低显示越多标签，值越高只保留高置信度标签")
        thresh_row.addWidget(gl)
        self._gen_slider = QSlider(Qt.Orientation.Horizontal, header)
        self._gen_slider.setRange(5, 95)
        self._gen_slider.setValue(35)
        self._gen_slider.setFixedHeight(14)
        thresh_row.addWidget(self._gen_slider, 1)
        self._gen_value = QLabel("0.35", header)
        self._gen_value.setFixedWidth(26)
        self._gen_value.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; font-family: monospace;")
        self._gen_slider.valueChanged.connect(lambda v: self._gen_value.setText(f"{v/100:.2f}"))
        thresh_row.addWidget(self._gen_value)
        thresh_row.addSpacing(6)
        cl = QLabel("角色", header)
        cl.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        cl.setToolTip("角色标签 (character/copyright/artist) 的最低置信度阈值\n"
                       "例如：hatsune_miku, vocaloid 等角色/作品名\n"
                       "通常需要较高阈值避免误判")
        thresh_row.addWidget(cl)
        self._char_slider = QSlider(Qt.Orientation.Horizontal, header)
        self._char_slider.setRange(5, 95)
        self._char_slider.setValue(70)
        self._char_slider.setFixedHeight(14)
        thresh_row.addWidget(self._char_slider, 1)
        self._char_value = QLabel("0.70", header)
        self._char_value.setFixedWidth(26)
        self._char_value.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; font-family: monospace;")
        self._char_slider.valueChanged.connect(lambda v: self._char_value.setText(f"{v/100:.2f}"))
        thresh_row.addWidget(self._char_value)
        right_col.addLayout(thresh_row)

        # Model path
        path_row = QHBoxLayout()
        path_row.setSpacing(4)
        self._path_display = QLabel("", header)
        self._path_display.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        path_row.addWidget(self._path_display, 1)
        browse_btn = QPushButton("📂", header)
        browse_btn.setFixedSize(16, 16)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setToolTip("切换模型目录")
        browse_btn.setStyleSheet(f"border: none; background: transparent; font-size: {_fs('fs_9')};")
        browse_btn.clicked.connect(self._browse_model_dir)
        path_row.addWidget(browse_btn)
        right_col.addLayout(path_row)

        h_layout.addLayout(right_col, 1)
        layout.addWidget(header)

        # ── Body ──
        body = QWidget(page)
        b_layout = QVBoxLayout(body)
        b_layout.setContentsMargins(10, 6, 10, 8)
        b_layout.setSpacing(4)

        # Status bar
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self._status = QLabel("", body)
        self._status.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        status_row.addWidget(self._status, 1)
        self._show_conf = True
        self._conf_btn = QPushButton("隐藏置信度", body)
        self._conf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._conf_btn.setFixedHeight(18)
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
        btn_row.setSpacing(8)
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
        btn.setText("安装中...")
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
                btn.setText("✓ 安装完成")
                btn.setEnabled(False)
                self._setup_status.setText("依赖已安装，点击下方按钮重启应用")
                restart_btn = QPushButton("重启应用", self)
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
                btn.setText("安装依赖 (onnxruntime + numpy)")
                btn.setEnabled(True)
                self._setup_status.setText(f"安装失败: {err}")

        self._install_worker = _InstallWorker(self)
        self._install_worker.finished.connect(_on_done)
        self._install_worker.start()

    def _prompt_python_setup(self, model_dir: str):
        """Show setup options when onnxruntime can't load directly."""
        self._pending_model_dir = model_dir
        self._stack.setCurrentIndex(0)
        self._setup_status.setText(
            "onnxruntime 无法在当前 Python 加载（版本不兼容）\n"
            "请点击「自动配置 Python 环境」或手动选择已安装 onnxruntime 的 Python"
        )

    def _browse_python(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Python 可执行文件", "",
            "Python (python.exe python3.exe);;All (*)"
        )
        if not path:
            return
        self._external_python = path
        self.python_path_changed.emit(path)
        if self._engine:
            self._engine.set_external_python(path)
        # Try to switch to ready if model already loaded
        model_dir = getattr(self, '_pending_model_dir', self._custom_model_dir)
        if model_dir and self._engine and self._engine._model_path:
            self._engine.load(
                self._engine._model_path, self._engine._mapping_path,
                external_python=path,
            )
            if self._engine.is_ready:
                self._switch_to_ready(model_dir)
                self.model_dir_changed.emit(model_dir)
                return
        self._setup_status.setText("✓ Python 路径已设置，请选择模型文件夹")

    # ───────────────── Auto Setup ─────────────────

    def _start_env_setup(self):
        """Start downloading and setting up embedded Python environment."""
        from ..python_env import PythonEnvSetupWorker
        if hasattr(self, '_auto_setup_btn'):
            self._auto_setup_btn.setEnabled(False)
            self._auto_setup_btn.setText("配置中...")
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

        # If model was already found, switch to ready
        model_dir = getattr(self, '_pending_model_dir', self._custom_model_dir)
        if self._engine and self._engine.is_ready and model_dir:
            self._switch_to_ready(model_dir)
            self.model_dir_changed.emit(model_dir)
        else:
            self._setup_status.setText("✓ Python 环境已配置，请选择模型文件夹")
            if hasattr(self, '_auto_setup_btn'):
                self._auto_setup_btn.setText("✓ 已配置")

    def _on_env_setup_error(self, error: str):
        self._setup_progress.hide()
        self._setup_status.setText(f"配置失败: {error}")
        if hasattr(self, '_auto_setup_btn'):
            self._auto_setup_btn.setEnabled(True)
            self._auto_setup_btn.setText("自动配置 Python 环境 (~200MB)")

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
            # Only go to ready page if engine can actually run inference
            can_infer = (not self._engine._use_subprocess) or self._engine._external_python
            if self._engine.is_ready and can_infer:
                self._switch_to_ready(os.path.dirname(model_path))
            else:
                # Model found but no working Python — show setup page
                self._stack.setCurrentIndex(0)
                self._pending_model_dir = os.path.dirname(model_path)
                self._setup_status.setText(
                    "模型已找到，但需要配置 Python 环境才能运行推理\n"
                    "请点击「自动配置 Python 环境」"
                )
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
        self._status.setText("✓ 模型已加载")

    def _browse_model_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择模型目录")
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
                                  external_python=self._external_python)
                if self._engine._use_subprocess and not self._external_python:
                    # Need external Python — prompt user for setup
                    self._prompt_python_setup(path)
                else:
                    self._switch_to_ready(path)
                    self.model_dir_changed.emit(path)
            except Exception as e:
                msg = f"加载失败: {e}"
                if hasattr(self, '_setup_status'):
                    self._setup_status.setText(msg)
                if hasattr(self, '_status'):
                    self._status.setText(msg)
        else:
            msg = "目录中未找到 .onnx + tag_mapping.json"
            if hasattr(self, '_setup_status'):
                self._setup_status.setText(msg)
            if hasattr(self, '_status'):
                self._status.setText(msg)

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
        self._status.setText("推理中...")
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
        self._status.setText(f"推理失败: {error}")
        # If subprocess/Python related, show setup page
        if self._engine and self._engine._use_subprocess:
            self._prompt_python_setup(self._custom_model_dir)

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
            self._conf_btn.setText("隐藏置信度")
            self._conf_btn.setStyleSheet(
                f"background: transparent; color: {p['text_dim']}; "
                f"border: 1px solid {p['line']}; border-radius: 3px; "
                f"padding: 0 6px; font-size: {_fs('fs_9')};"
            )
        else:
            self._conf_btn.setText("显示置信度")
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
#  LLM Vision Tab
# ═══════════════════════════════════════════════════

class _LLMTaggerTab(QWidget):
    """Tab for LLM multimodal image tagging."""

    send_to_input = pyqtSignal(str)

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self._t = translator
        self._image_path: str | None = None
        self._worker = None

        p = current_palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Drop zone ──
        self._drop_zone = _DropZone(translator, self)
        self._drop_zone.image_selected.connect(self._on_image_selected)
        root.addWidget(self._drop_zone)

        # ── Prompt ──
        prompt_label = QLabel(translator.t("interrogator_llm_prompt"), self)
        prompt_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        root.addWidget(prompt_label)

        self._prompt_edit = QTextEdit(self)
        self._prompt_edit.setMaximumHeight(60)
        self._prompt_edit.setPlainText(translator.t("interrogator_llm_default_prompt"))
        self._prompt_edit.setStyleSheet(
            f"background: {p['bg_input']}; color: {p['text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 4px; font-size: {_fs('fs_10')};"
        )
        root.addWidget(self._prompt_edit)

        # ── Start button ──
        self._start_btn = QPushButton(translator.t("interrogator_start"), self)
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._start_inference)
        root.addWidget(self._start_btn)

        # ── Status ──
        self._status = QLabel("", self)
        self._status.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        root.addWidget(self._status)

        # ── Result ──
        self._result_edit = QTextEdit(self)
        self._result_edit.setReadOnly(True)
        self._result_edit.setStyleSheet(
            f"background: {p['bg_input']}; color: {p['text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px; font-size: {_fs('fs_10')};"
        )
        root.addWidget(self._result_edit, 1)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton(translator.t("copy"), self)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(self._result_edit.toPlainText())
        )
        btn_row.addWidget(copy_btn)
        send_btn = QPushButton(translator.t("interrogator_send_to_input"), self)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.clicked.connect(
            lambda: self.send_to_input.emit(self._result_edit.toPlainText()) if self._result_edit.toPlainText() else None
        )
        btn_row.addWidget(send_btn)
        root.addLayout(btn_row)

        # API settings reference (filled by window.py)
        self._api_base_url = ""
        self._api_key = ""
        self._model = ""

    def set_api_settings(self, base_url: str, api_key: str, model: str):
        self._api_base_url = base_url
        self._api_key = api_key
        self._model = model

    def _on_image_selected(self, path: str):
        self._image_path = path

    def _start_inference(self):
        if not self._image_path:
            self._status.setText(self._t.t("interrogator_no_image"))
            return
        if not self._api_base_url or not self._api_key or not self._model:
            self._status.setText(self._t.t("error_missing_api"))
            return

        self._status.setText("推理中...")
        self._result_edit.clear()
        self._start_btn.setEnabled(False)

        # Build message with image
        prompt_text = self._prompt_edit.toPlainText().strip()
        with open(self._image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(self._image_path).suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")

        messages = [
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt_text},
            ]}
        ]

        from ..api_client import ChatWorker
        from ..logic import normalize_api_base_url
        base_url = normalize_api_base_url(self._api_base_url)
        payload = {"model": self._model, "messages": messages, "max_tokens": 4096, "stream": True}

        self._worker = ChatWorker(
            f"{base_url}/chat/completions", payload, self._api_key, stream=True, summary_mode=False
        )
        self._worker.delta_received.connect(self._on_delta)
        self._worker.error_received.connect(self._on_error)
        self._worker.finished_cleanly.connect(self._on_finished)
        self._worker.start()

    def _on_delta(self, text: str):
        cursor = self._result_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)

    def _on_error(self, message: str, status_code: int, details: str):
        self._status.setText(f"[Error] {message}")
        self._start_btn.setEnabled(True)

    def _on_finished(self):
        self._status.setText("✓ 推理完成")
        self._start_btn.setEnabled(True)


# ═══════════════════════════════════════════════════
#  Drop Zone (shared)
# ═══════════════════════════════════════════════════

class _DropZone(QFrame):
    """Image drop zone with preview."""

    image_selected = pyqtSignal(str)

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self._t = translator
        self.setAcceptDrops(True)
        self.setMinimumHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        p = current_palette()
        self.setStyleSheet(
            f"background: {p['bg_input']}; border: 2px dashed {p['line_strong']}; border-radius: 6px;"
        )

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel(translator.t("interrogator_drop_image"), self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; border: none;")
        layout.addWidget(self._label)

        self._preview = QLabel(self)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.hide()
        layout.addWidget(self._preview)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, self._t.t("interrogator_select_image"), "",
                "Images (*.png *.jpg *.jpeg *.webp);;All (*)"
            )
            if path:
                self._set_image(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self._set_image(path)

    def _set_image(self, path: str):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        # Scale to fit parent size
        max_h = max(40, self.height() - 30)
        scaled = pixmap.scaled(max_h, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._preview.setPixmap(scaled)
        self._preview.show()
        self._label.setText(os.path.basename(path))
        self.image_selected.emit(path)


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

    def apply_theme(self):
        # Rebuild pages to pick up new palette + font sizes
        self._local_tab._rebuild_pages()
        # LLM tab has fewer custom styles, but refresh result area
        p = current_palette()
        self._llm_tab._result_edit.setStyleSheet(
            f"background: {p['bg_input']}; color: {p['text']}; "
            f"border: 1px solid {p['line']}; border-radius: 4px; "
            f"padding: 6px; font-size: {_fs('fs_10')};"
        )

    def retranslate_ui(self):
        self._tabs.setTabText(0, self._t.t("interrogator_local"))
        self._tabs.setTabText(1, self._t.t("interrogator_llm"))
