"""Image Interrogator — local tagger + LLM vision tag inference."""
from __future__ import annotations

import base64
import os
import sys
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

from ..i18n import Translator
from ..file_filters import image_filter, python_filter
from ..theme import _fs, current_palette, is_theme_light
from ..ui_tokens import _dp
from .output_widget import CATEGORY_COLORS, CATEGORY_COLORS_LIGHT


_LOCAL_TAGGER_CATEGORIES = ("general", "character", "copyright", "meta", "model", "rating", "quality", "artist")
_DANBOORU_CATEGORY_SEMANTIC = {
    0: "appearance",
    1: "style",
    3: "style",
    4: "character",
    5: "style",
}
_LOCAL_CATEGORY_SEMANTIC = {
    "general": "appearance",
    "character": "character",
    "copyright": "style",
    "artist": "style",
    "meta": "style",
    "model": "style",
    "rating": "emotion",
    "quality": "style",
}
_LOCAL_SEMANTIC_KEYS = {
    "character": "tag_category_character",
    "scene": "tag_category_scene",
    "pose": "tag_category_pose",
    "clothing": "tag_category_clothing",
    "expression": "tag_category_expression",
    "body": "tag_category_body",
    "style": "tag_category_style",
    "quality": "tag_category_quality",
    "lighting": "tag_category_lighting",
    "camera": "tag_category_camera",
    "effect": "tag_category_effect",
    "nsfw": "tag_category_nsfw",
    "action": "tag_category_action",
    "accessory": "tag_category_accessory",
    "text": "tag_category_text",
}
_LOCAL_CATEGORY_LABEL_KEYS = {
    "general": "local_category_general",
    "character": "local_category_character",
    "copyright": "local_category_copyright",
    "meta": "local_category_meta",
    "model": "local_category_model",
    "rating": "local_category_rating",
    "quality": "local_category_quality",
    "artist": "local_category_artist",
}


def _semantic_colors() -> dict[str, str]:
    return CATEGORY_COLORS_LIGHT if is_theme_light() else CATEGORY_COLORS


def _semantic_category_color(category: str, fallback: str = "appearance") -> str:
    colors = _semantic_colors()
    semantic = _LOCAL_CATEGORY_SEMANTIC.get(category, category or fallback)
    return colors.get(semantic, colors.get(fallback, next(iter(colors.values()))))


def _semantic_category_label(translator: Translator | None, category: str) -> str:
    key = _LOCAL_SEMANTIC_KEYS.get(category, "")
    if translator is None or not key:
        return category
    label = translator.t(key)
    return label if label != key else category


def _local_category_label(translator: Translator, category: str) -> str:
    key = _LOCAL_CATEGORY_LABEL_KEYS.get(category, "")
    if not key:
        return category
    label = translator.t(key)
    return label if label != key else category


def _danbooru_category_color(category_id: int | None) -> str:
    colors = _semantic_colors()
    semantic = _DANBOORU_CATEGORY_SEMANTIC.get(category_id if category_id is not None else 0, "appearance")
    return colors.get(semantic, colors["appearance"])


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _semantic_category_for_tag(info, tag: str, fallback_category: str) -> str:
    """Map local-tagger results to the shared workbench semantic categories."""
    if fallback_category in _LOCAL_CATEGORY_SEMANTIC and fallback_category != "general":
        return _LOCAL_CATEGORY_SEMANTIC[fallback_category]

    norm = tag.strip().lower().replace(" ", "_")
    group = str(getattr(info, "group", "") or "")
    subgroup = str(getattr(info, "subgroup", "") or "")
    hay = f"{group} {subgroup} {norm}"
    category_id = getattr(info, "category_id", None)

    if category_id == 4 or _contains_any(norm, ("1girl", "1boy", "solo", "multiple_girls", "multiple_boys")):
        return "character"
    if category_id in {1, 3}:
        return "style"
    if category_id == 5:
        return "quality"

    if _contains_any(hay, ("表情", "情绪", "脸红", "嘴巴", "眼神", "泪", "笑", "哭", "舌", "瞳孔", "smile", "blush", "tears", "crying", "tongue", "pout")):
        return "expression"
    if _contains_any(hay, ("服", "裙", "裤", "袜", "鞋", "帽", "手套", "制服", "首饰", "饰品", "发饰", "项圈", "眼镜", "领带", "dress", "skirt", "shirt", "uniform", "panties", "bra", "socks", "thighhighs", "shoes", "boots", "jacket", "coat", "sweater", "kimono", "swimsuit", "bikini", "ribbon", "glasses", "collar")):
        return "clothing"
    if _contains_any(hay, ("视角", "构图", "镜头", "焦点", "裁切", "特写", "景深", "pov", "from_", "view", "close-up", "focus", "depth_of_field")):
        return "camera"
    if _contains_any(hay, ("姿势", "动作", "手势", "视线", "站", "坐", "躺", "蹲", "跪", "holding", "looking", "standing", "sitting", "lying", "kneeling", "squatting", "walking", "running", "spread_", "hands", "arms")):
        return "pose"
    if _contains_any(hay, ("场景", "背景", "室内", "室外", "天空", "水", "森林", "城市", "房间", "自然", "indoors", "outdoors", "room", "classroom", "bedroom", "school", "city", "street", "forest", "beach", "sky", "water", "night", "day", "window")):
        return "scene"
    if _contains_any(hay, ("光", "阴影", "照明", "lighting", "shadow", "sunlight", "backlight")):
        return "lighting"
    if _contains_any(hay, ("效果", "模糊", "速度线", "闪光", "花瓣", "motion", "blur", "sparkle")):
        return "effect"
    if _contains_any(hay, ("发型", "发色", "眼睛", "瞳色", "肤色", "体型", "对象", "种族", "角色", "_hair", "_eyes", "hair_", "eye_", "skin", "fang", "animal_ears", "horns")):
        return "character"
    if _contains_any(hay, ("身体", "皮肤", "胸", "臀", "腿", "脚", "手", "尾", "耳", "角", "翅", "汗", "湿")):
        return "body"
    if _contains_any(hay, ("质量", "画风", "风格", "masterpiece", "quality", "style", "year_")):
        return "quality"
    if _contains_any(hay, ("文字", "符号", "标志", "text", "symbol", "logo")):
        return "text"
    if _contains_any(hay, ("nsfw", "rating", "explicit", "questionable")):
        return "nsfw"
    return _LOCAL_CATEGORY_SEMANTIC.get(fallback_category, "quality")


def _local_colors() -> dict[str, str]:
    p = current_palette()
    return {
        "bg0": p["bg_input"],
        "bg1": p["bg_content"],
        "bg2": p["bg_surface"],
        "bg3": p["hover_bg_strong"],
        "line": p["line"],
        "line2": p["line_strong"],
        "dash": p["line_hover"],
        "fg0": p["text"],
        "fg1": p["text_body"],
        "fg2": p["text_muted"],
        "fg3": p["text_dim"],
        "accent": p["accent"],
        "accent_hover": p["accent_hover"],
        "accent_text": p["accent_text"],
        "hot": p["close_hover"],
        "ok": p["accent_text_hover"],
        "warn": p["accent_handle"],
    }


def _local_button_style(*, primary: bool = False, compact: bool = False) -> str:
    c = _local_colors()
    bg = c["fg0"] if primary else "transparent"
    fg = c["bg0"] if primary else c["fg1"]
    border = c["fg0"] if primary else c["line2"]
    pad = "0px 8px" if compact else "6px 12px"
    return (
        f"QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {border}; "
        f"border-radius: 3px; padding: {pad}; font-size: {_fs('fs_10')}; letter-spacing: 0.04em; }}"
        f"QPushButton:hover {{ background: {c['accent_hover'] if primary else c['bg3']}; "
        f"color: {c['bg0'] if primary else c['fg0']}; border-color: {c['fg3'] if not primary else c['accent_hover']}; }}"
        f"QPushButton:disabled {{ color: {c['fg3']}; border-color: {c['line']}; background: transparent; }}"
    )


def _square_icon(color: str, size: int = 5) -> QIcon:
    pixmap = QPixmap(_dp(size), _dp(size))
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class _LocalTagChip(QLabel):
    def __init__(
        self,
        text: str,
        category: str,
        probability: float | None,
        show_confidence: bool,
        *,
        category_id: int | None = None,
        semantic_category: str = "",
        translation: str = "",
        translator: Translator | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._text = text
        self._category = category
        self._category_id = category_id
        self._semantic_category = semantic_category
        self._translation = translation
        self._probability = probability
        self._show_confidence = show_confidence
        self.setText(self._display_text())
        self.setFixedHeight(_dp(22))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        tip_parts = []
        if translation:
            tip_parts.append(translation)
        if semantic_category:
            tip_parts.append(_semantic_category_label(translator, semantic_category))
        if tip_parts:
            self.setToolTip(" · ".join(tip_parts))
        self.apply_theme()

    def _display_text(self) -> str:
        if self._show_confidence and self._probability is not None:
            return f"{self._text}  {self._probability:.3f}"
        return self._text

    def apply_theme(self) -> None:
        semantic_colors = _semantic_colors()
        if self._semantic_category in semantic_colors:
            color = semantic_colors[self._semantic_category]
        elif self._category_id is not None:
            color = _danbooru_category_color(self._category_id)
        else:
            color = _semantic_category_color(self._category)
        fg = _readable_text_for_hex(color) if "_readable_text_for_hex" in globals() else "#ffffff"
        self.setStyleSheet(
            f"background: {color}; color: {fg}; border: none; border-radius: 2px; "
            f"padding: 0px {_dp(8)}px; font-size: {_fs('fs_10')};"
        )


# ═══════════════════════════════════════════════════
#  Local Tagger Tab
# ═══════════════════════════════════════════════════

class _LocalTaggerTab(QWidget):
    """Tab for local cl_tagger ONNX inference. Two states: setup guide / inference."""

    send_to_input = pyqtSignal(str)
    model_dir_changed = pyqtSignal(str)
    python_path_changed = pyqtSignal(str)
    settings_changed = pyqtSignal()
    mode_changed = pyqtSignal(int)

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
        self._last_error_text: str = ""
        self._installing_env: bool = False
        self._last_results: dict | None = None
        self._tag_dict = None
        self._populating_settings = False
        self._local_preview_ratio = 22
        self._local_general_threshold = 35
        self._local_character_threshold = 70
        self._show_conf = True

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

    def _lt(self, key: str, fallback: str) -> str:
        text = self._t.t(key)
        return fallback if text == key else text

    def set_tag_dictionary(self, dictionary) -> None:
        self._tag_dict = dictionary
        self._render_results()

    def apply_local_settings(self, settings) -> None:
        self._populating_settings = True
        categories = getattr(settings, "tagger_local_enabled_categories", None)
        if isinstance(categories, (list, tuple, set)):
            enabled = {str(cat) for cat in categories if str(cat) in _LOCAL_TAGGER_CATEGORIES}
            if enabled:
                self._enabled_categories = enabled
        self._local_preview_ratio = max(12, min(70, int(getattr(settings, "tagger_local_preview_ratio", 22) or 22)))
        self._show_conf = bool(getattr(settings, "tagger_local_show_confidence", True))
        gen_threshold = max(5, min(95, int(getattr(settings, "tagger_local_general_threshold", 35) or 35)))
        char_threshold = max(5, min(95, int(getattr(settings, "tagger_local_character_threshold", 70) or 70)))
        self._local_general_threshold = gen_threshold
        self._local_character_threshold = char_threshold
        if hasattr(self, "_gen_slider"):
            self._gen_slider.setValue(gen_threshold)
            self._gen_value.setText(f"{gen_threshold/100:.2f}")
        if hasattr(self, "_char_slider"):
            self._char_slider.setValue(char_threshold)
            self._char_value.setText(f"{char_threshold/100:.2f}")
        if hasattr(self, "_conf_btn"):
            self._conf_btn.setText(self._t.t("interr_hide_conf") if self._show_conf else self._t.t("interr_show_conf"))
        self._apply_cat_styles()
        self._apply_local_splitter_ratio()
        self._render_results()
        self._populating_settings = False

    def collect_local_settings(self) -> dict:
        return {
            "tagger_local_enabled_categories": [cat for cat in _LOCAL_TAGGER_CATEGORIES if cat in self._enabled_categories],
            "tagger_local_general_threshold": self._local_general_threshold,
            "tagger_local_character_threshold": self._local_character_threshold,
            "tagger_local_show_confidence": self._show_conf,
            "tagger_local_preview_ratio": self._local_preview_ratio,
            "tagger_local_layout_v2": True,
        }

    # ───────────────── Setup Page ─────────────────

    def _build_setup_page(self) -> QWidget:
        p = current_palette()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget(page)
        header.setObjectName("LocalSetupHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(_dp(14), _dp(12), _dp(14), _dp(10))
        header_layout.setSpacing(_dp(8))

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._setup_mode_switch = _InterrogatorModeSwitch(self._t, header)
        self._setup_mode_switch.mode_changed.connect(self.mode_changed.emit)
        top.addWidget(self._setup_mode_switch)
        top.addStretch()
        flavor = QLabel(self._t.t("interr_local_engine_offline"), header)
        flavor.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')}; letter-spacing: 0.08em;")
        top.addWidget(flavor)
        header_layout.addLayout(top)

        title = QLabel(self._t.t("interr_setup_title"), page)
        title.setStyleSheet(f"color: {p['text']}; font-size: {_fs('fs_14')}; font-weight: bold;")
        header_layout.addWidget(title)

        desc = QLabel(self._t.t("interr_setup_desc"), page)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; line-height: 1.55;")
        header_layout.addWidget(desc)
        layout.addWidget(header)

        body = QWidget(page)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        scroll = QScrollArea(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        steps_host = QWidget()
        steps_layout = QVBoxLayout(steps_host)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.setSpacing(0)

        self._setup_model_path = QLabel("", steps_host)
        self._setup_python_path = QLabel("", steps_host)
        self._setup_model_error = QLabel("", steps_host)
        self._setup_model_error.setWordWrap(True)
        self._setup_model_error.hide()
        self._setup_python_error = QLabel("", steps_host)
        self._setup_python_error.setWordWrap(True)
        self._setup_python_error.hide()

        link_btn = QPushButton(self._t.t("interr_open_download"), steps_host)
        link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_btn.setStyleSheet(_local_button_style())
        link_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://huggingface.co/cella110n/cl_tagger/tree/main/cl_tagger_1_02")
        ))
        select_btn = QPushButton(self._t.t("interr_select_model_dir"), steps_host)
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_btn.setStyleSheet(_local_button_style(primary=True))
        select_btn.clicked.connect(self._browse_model_dir)
        model_actions = [link_btn, select_btn]

        model_step = self._create_local_step(
            steps_host,
            "01",
            self._lt("interr_local_model_step_title", "下载并定位模型"),
            self._lt("interr_local_model_step_desc", "需要 model_optimized.onnx 与 tag_mapping.json，放在同一文件夹。"),
            [self._setup_model_path, *model_actions, self._setup_model_error],
        )
        self._setup_model_step = model_step
        steps_layout.addWidget(model_step)

        self._auto_setup_btn = QPushButton(self._t.t("interr_auto_setup"), steps_host)
        self._auto_setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auto_setup_btn.setStyleSheet(_local_button_style(primary=True))
        self._auto_setup_btn.clicked.connect(self._start_env_setup)
        manual_btn = QPushButton(self._t.t("interr_manual_python"), steps_host)
        manual_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manual_btn.setStyleSheet(_local_button_style())
        manual_btn.clicked.connect(self._browse_python)

        self._setup_progress = QProgressBar(steps_host)
        self._setup_progress.setRange(0, 100)
        self._setup_progress.setTextVisible(False)
        self._setup_progress.setFixedHeight(_dp(3))
        self._setup_progress.hide()

        self._setup_status = QLabel("", steps_host)
        self._setup_status.setWordWrap(True)
        self._setup_status.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")

        python_step = self._create_local_step(
            steps_host,
            "02",
            self._lt("interr_local_python_step_title", "配置推理环境"),
            self._lt("interr_local_python_step_desc", "优先进程内 onnxruntime；不可用时回退到外部 Python 子进程。"),
            [self._auto_setup_btn, self._setup_python_path, manual_btn, self._setup_progress, self._setup_status, self._setup_python_error],
        )
        self._setup_python_step = python_step
        steps_layout.addWidget(python_step)

        self._start_ready_btn = QPushButton(self._t.t("interr_start_using") + " →", steps_host)
        self._start_ready_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_ready_btn.setStyleSheet(_local_button_style(primary=True))
        self._start_ready_btn.clicked.connect(self._confirm_and_switch)
        self._start_ready_btn.hide()
        ready_step = self._create_local_step(
            steps_host,
            "03",
            self._lt("interr_local_ready_step_title", "就绪"),
            self._lt("interr_local_ready_step_desc", "所有检查项通过，可以进入推理页对单张图片进行反推。"),
            [self._start_ready_btn],
        )
        self._setup_ready_step = ready_step
        steps_layout.addWidget(ready_step)
        steps_layout.addStretch()
        scroll.setWidget(steps_host)
        body_layout.addWidget(scroll, 1)

        status_panel = QWidget(body)
        status_panel.setFixedWidth(_dp(200))
        status_panel.setObjectName("LocalStatusPanel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)
        status_title = QLabel(self._lt("interr_local_status_title", "状态"), status_panel)
        status_title.setStyleSheet(
            f"background: {p['bg_surface']}; color: {p['text_dim']}; "
            f"border-bottom: 1px solid {p['line']}; padding: {_dp(8)}px {_dp(12)}px; "
            f"font-size: {_fs('fs_9')}; letter-spacing: 0.08em;"
        )
        status_layout.addWidget(status_title)
        self._setup_leds: dict[str, QLabel] = {}
        self._setup_status_values: dict[str, QLabel] = {}
        for key, label in (
            ("model", self._lt("interr_local_status_model", "模型")),
            ("ort", "onnxruntime"),
            ("python", "Python"),
        ):
            row = self._create_status_row(status_panel, key, label)
            status_layout.addWidget(row)
        status_layout.addStretch()
        hint = QLabel(self._lt("interr_local_status_hint", "优先进程内 ORT 推理；子进程仅作回退方案。上次目录会自动记忆。"), status_panel)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {p['text_dim']}; border-top: 1px solid {p['line']}; "
            f"padding: {_dp(12)}px; font-size: {_fs('fs_9')}; line-height: 1.6;"
        )
        status_layout.addWidget(hint)
        body_layout.addWidget(status_panel)
        layout.addWidget(body, 1)

        footer = QLabel(self._t.t("interr_local_engine_footer"), page)
        footer.setStyleSheet(
            f"background: {p['bg_surface']}; color: {p['text_dim']}; "
            f"border-top: 1px solid {p['line']}; padding: {_dp(6)}px {_dp(12)}px; font-size: {_fs('fs_9')};"
        )
        layout.addWidget(footer)

        self._refresh_setup_view()
        return page

    # ───────────────── Ready Page ─────────────────

    def _build_ready_page(self) -> QWidget:
        p = current_palette()
        c = _local_colors()
        page = QWidget()
        page.setObjectName("LocalReadyPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget(page)
        toolbar.setObjectName("LocalInferToolbar")
        toolbar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(8))
        toolbar_layout.setSpacing(_dp(6))

        row1 = QHBoxLayout()
        row1.setSpacing(_dp(6))
        self._ready_mode_switch = _InterrogatorModeSwitch(self._t, toolbar)
        self._ready_mode_switch.mode_changed.connect(self.mode_changed.emit)
        row1.addWidget(self._ready_mode_switch, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._category_wrap = QWidget(toolbar)
        self._category_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._category_wrap.setMinimumHeight(_dp(20))
        self._category_wrap.setMaximumHeight(_dp(46))
        self._category_flow = _FlowLayout(self._category_wrap, spacing=_dp(6))
        self._category_flow.setContentsMargins(0, 0, 0, 0)
        self._cat_buttons: dict[str, QPushButton] = {}
        for cat in _LOCAL_TAGGER_CATEGORIES:
            btn = QPushButton(cat, toolbar)
            btn.setIcon(_square_icon(_semantic_category_color(cat)))
            btn.setIconSize(QSize(_dp(5), _dp(5)))
            btn.setCheckable(True)
            btn.setChecked(cat in self._enabled_categories)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_dp(20))
            btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(partial(self._toggle_category, cat))
            self._cat_buttons[cat] = btn
            self._category_flow.addWidget(btn)
        row1.addWidget(self._category_wrap, 1)
        toolbar_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(_dp(8))
        gl = QLabel(self._t.t("interr_general"), toolbar)
        gl.setFixedWidth(_dp(32))
        gl.setStyleSheet(f"color: {p['text_body']}; font-size: {_fs('fs_9')};")
        gl.setToolTip(self._t.t("interr_general_tip"))
        row2.addWidget(gl)
        self._gen_slider = QSlider(Qt.Orientation.Horizontal, toolbar)
        self._gen_slider.setMinimumWidth(_dp(90))
        self._gen_slider.setRange(5, 95)
        self._gen_slider.setValue(self._local_general_threshold)
        self._gen_slider.setFixedHeight(_dp(16))
        row2.addWidget(self._gen_slider, 1)
        self._gen_value = QLabel(f"{self._local_general_threshold/100:.2f}", toolbar)
        self._gen_value.setFixedWidth(_dp(36))
        self._gen_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._gen_value.setStyleSheet(f"color: {p['text_body']}; font-size: {_fs('fs_9')};")
        self._gen_slider.valueChanged.connect(lambda v: self._on_local_threshold_changed("general", self._gen_value, v))
        row2.addWidget(self._gen_value)
        cl = QLabel(self._t.t("interr_character_label"), toolbar)
        cl.setFixedWidth(_dp(32))
        cl.setStyleSheet(f"color: {p['text_body']}; font-size: {_fs('fs_9')};")
        cl.setToolTip(self._t.t("interr_character_tip"))
        row2.addWidget(cl)
        self._char_slider = QSlider(Qt.Orientation.Horizontal, toolbar)
        self._char_slider.setMinimumWidth(_dp(90))
        self._char_slider.setRange(5, 95)
        self._char_slider.setValue(self._local_character_threshold)
        self._char_slider.setFixedHeight(_dp(16))
        row2.addWidget(self._char_slider, 1)
        self._char_value = QLabel(f"{self._local_character_threshold/100:.2f}", toolbar)
        self._char_value.setFixedWidth(_dp(36))
        self._char_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._char_value.setStyleSheet(f"color: {p['text_body']}; font-size: {_fs('fs_9')};")
        self._char_slider.valueChanged.connect(lambda v: self._on_local_threshold_changed("character", self._char_value, v))
        row2.addWidget(self._char_value)
        toolbar_layout.addLayout(row2)
        layout.addWidget(toolbar)

        path_bar = QWidget(page)
        path_bar.setObjectName("LocalPathBar")
        path_row = QHBoxLayout()
        path_row.setContentsMargins(_dp(10), 0, _dp(10), 0)
        path_row.setSpacing(_dp(8))
        path_bar.setFixedHeight(_dp(38))
        self._local_run_dot = QLabel("●", path_bar)
        path_row.addWidget(self._local_run_dot)
        self._status = QLabel("", path_bar)
        self._status.setStyleSheet(f"color: {p['text_body']}; font-size: {_fs('fs_10')};")
        path_row.addWidget(self._status)
        path_row.addStretch()
        self._path_display = QLabel("", path_bar)
        self._path_display.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._path_display.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        path_row.addWidget(self._path_display, 1)
        browse_btn = QPushButton("…", path_bar)
        browse_btn.setFixedSize(_dp(26), _dp(26))
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setToolTip(self._t.t("interr_browse_dir_tip"))
        browse_btn.setStyleSheet(_local_button_style(compact=True))
        browse_btn.clicked.connect(self._browse_model_dir)
        path_row.addWidget(browse_btn)
        path_bar.setLayout(path_row)
        layout.addWidget(path_bar)

        main = QSplitter(Qt.Orientation.Horizontal, page)
        self._local_splitter = main
        main.setObjectName("LocalInferMainSplitter")
        main.setChildrenCollapsible(False)
        main.setHandleWidth(_dp(3))
        main.splitterMoved.connect(self._on_local_splitter_moved)

        image_col = QWidget(main)
        image_col.setObjectName("LocalImageColumn")
        image_col.setMinimumWidth(_dp(130))
        image_layout = QVBoxLayout(image_col)
        image_layout.setContentsMargins(_dp(10), _dp(10), _dp(10), _dp(10))
        image_layout.setSpacing(_dp(8))
        self._drop_zone = _DropZone(self._t, image_col)
        self._drop_zone.setObjectName("LocalSingleDrop")
        self._drop_zone.setMinimumHeight(_dp(120))
        self._drop_zone.image_selected.connect(self._on_image_selected)
        image_layout.addWidget(self._drop_zone, 1)
        self._change_image_btn = QPushButton(self._t.t("change_image"), image_col)
        self._change_image_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._change_image_btn.setStyleSheet(_local_button_style())
        self._change_image_btn.clicked.connect(self._select_local_image)
        image_layout.addWidget(self._change_image_btn)
        main.addWidget(image_col)

        result_scroll = QScrollArea(main)
        result_scroll.setObjectName("LocalResultScroll")
        result_scroll.setWidgetResizable(True)
        result_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._result_container = QWidget()
        self._result_container.setObjectName("LocalResultContainer")
        self._result_layout = QVBoxLayout(self._result_container)
        self._result_layout.setContentsMargins(0, 0, 0, 0)
        self._result_layout.setSpacing(0)
        self._empty_result_label = QLabel(self._lt("interr_select_image_to_start", "选择一张图片以开始推理"), self._result_container)
        self._empty_result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_result_label.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_10')}; padding: {_dp(24)}px;")
        self._result_layout.addWidget(self._empty_result_label, 1)
        result_scroll.setWidget(self._result_container)
        main.addWidget(result_scroll)
        self._apply_local_splitter_ratio()
        layout.addWidget(main, 1)

        footer = QWidget(page)
        footer.setObjectName("LocalInferFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(_dp(12), _dp(6), _dp(12), _dp(6))
        footer_layout.setSpacing(_dp(8))
        footer.setFixedHeight(_dp(40))
        self._footer_status = QLabel("", footer)
        self._footer_status.setStyleSheet(f"color: {p['text_dim']}; font-size: {_fs('fs_9')};")
        footer_layout.addWidget(self._footer_status, 1)
        self._conf_btn = QPushButton(
            self._t.t("interr_hide_conf") if self._show_conf else self._t.t("interr_show_conf"),
            footer,
        )
        self._conf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._conf_btn.setStyleSheet(_local_button_style())
        self._conf_btn.clicked.connect(self._toggle_confidence)
        footer_layout.addWidget(self._conf_btn)
        self._copy_btn = QPushButton(self._t.t("copy"), footer)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setStyleSheet(_local_button_style())
        self._copy_btn.clicked.connect(self._copy_result)
        footer_layout.addWidget(self._copy_btn)
        self._send_btn = QPushButton(self._t.t("interrogator_send_to_input") + " →", footer)
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(_local_button_style(primary=True))
        self._send_btn.clicked.connect(self._send_result)
        footer_layout.addWidget(self._send_btn)
        layout.addWidget(footer)

        self._apply_cat_styles()
        self._apply_local_ready_theme(page)
        self._refresh_ready_status()
        QTimer.singleShot(0, self._refresh_category_wrap_height)
        QTimer.singleShot(0, self._apply_local_splitter_ratio)
        return page

    # ───────────────── Local UI helpers ─────────────────

    def _create_local_step(self, parent, num: str, title: str, desc: str, widgets: list[QWidget]) -> QFrame:
        c = _local_colors()
        frame = QFrame(parent)
        frame.setProperty("state", "idle")
        row = QHBoxLayout(frame)
        row.setContentsMargins(_dp(12), _dp(12), _dp(12), _dp(12))
        row.setSpacing(_dp(10))

        num_label = QLabel(num, frame)
        num_label.setObjectName("LocalStepNum")
        num_label.setFixedWidth(_dp(26))
        num_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        row.addWidget(num_label)

        body = QWidget(frame)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(_dp(6))

        title_label = QLabel(title, body)
        title_label.setObjectName("LocalStepTitle")
        body_layout.addWidget(title_label)

        desc_label = QLabel(desc, body)
        desc_label.setObjectName("LocalStepDesc")
        desc_label.setWordWrap(True)
        body_layout.addWidget(desc_label)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(_dp(6))
        for widget in widgets:
            if isinstance(widget, QLabel):
                widget.setStyleSheet(
                    f"background: {c['bg0']}; color: {c['fg2']}; border: 1px solid {c['line']}; "
                    f"border-radius: 2px; padding: {_dp(5)}px {_dp(7)}px; font-size: {_fs('fs_9')};"
                )
                widget.setMinimumHeight(_dp(24))
                widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                body_layout.addWidget(widget)
            elif isinstance(widget, QProgressBar):
                widget.setStyleSheet(
                    f"QProgressBar {{ background: {c['bg0']}; border: none; border-radius: 1px; }}"
                    f"QProgressBar::chunk {{ background: {c['accent_text']}; border-radius: 1px; }}"
                )
                body_layout.addWidget(widget)
            elif isinstance(widget, QPushButton):
                action_row.addWidget(widget)
            else:
                body_layout.addWidget(widget)
        if action_row.count():
            action_row.addStretch()
            body_layout.addLayout(action_row)

        row.addWidget(body, 1)
        self._style_local_step(frame)
        return frame

    def _style_local_step(self, frame: QFrame, state: str = "idle") -> None:
        c = _local_colors()
        frame.setProperty("state", state)
        accent = {
            "done": c["ok"],
            "active": c["accent_text"],
            "error": c["hot"],
        }.get(state, c["fg3"])
        bg = c["bg2"] if state == "active" else "transparent"
        frame.setStyleSheet(
            f"QFrame {{ background: {bg}; border-bottom: 1px solid {c['line']}; }}"
            f"QLabel#LocalStepNum {{ color: {accent}; font-size: {_fs('fs_10')}; font-weight: bold; "
            f"background: transparent; border: none; padding: 0px; }}"
            f"QLabel#LocalStepTitle {{ color: {c['fg0']}; font-size: {_fs('fs_11')}; font-weight: bold; "
            f"background: transparent; border: none; padding: 0px; }}"
            f"QLabel#LocalStepDesc {{ color: {c['fg2']}; font-size: {_fs('fs_9')}; "
            f"background: transparent; border: none; padding: 0px; }}"
        )

    def _apply_local_ready_theme(self, page: QWidget | None = None) -> None:
        c = _local_colors()
        page = page or getattr(self, "_ready_page", None)
        if page is None:
            return
        slider_style = (
            f"QSlider {{ background: transparent; }}"
            f"QSlider::groove:horizontal {{ height: 1px; background: {c['line2']}; margin: 7px 0px; }}"
            f"QSlider::sub-page:horizontal {{ height: 1px; background: {c['fg2']}; margin: 7px 0px; }}"
            f"QSlider::add-page:horizontal {{ height: 1px; background: {c['line2']}; margin: 7px 0px; }}"
            f"QSlider::handle:horizontal {{ width: 10px; height: 10px; margin: -5px 0px; "
            f"border-radius: 5px; background: {c['fg1']}; border: none; }}"
            f"QSlider::handle:horizontal:hover {{ background: {c['fg0']}; }}"
        )
        page.setStyleSheet(
            f"QWidget#LocalReadyPage {{ background: {c['bg1']}; }}"
            f"QWidget#LocalInferToolbar {{ background: {c['bg2']}; border-bottom: 1px solid {c['line']}; }}"
            f"QWidget#LocalPathBar {{ background: {c['bg1']}; border-bottom: 1px solid {c['line']}; }}"
            f"QSplitter#LocalInferMainSplitter {{ background: {c['bg1']}; }}"
            f"QSplitter#LocalInferMainSplitter::handle:horizontal {{ background: {c['line']}; width: 3px; margin: 0px; }}"
            f"QSplitter#LocalInferMainSplitter::handle:horizontal:hover {{ background: {c['fg3']}; }}"
            f"QWidget#LocalImageColumn {{ background: {c['bg1']}; border-right: 1px solid {c['line']}; }}"
            f"QWidget#LocalInferFooter {{ background: {c['bg2']}; border-top: 1px solid {c['line']}; }}"
            f"QScrollArea#LocalResultScroll {{ background: {c['bg1']}; border: none; }}"
            f"QWidget#LocalResultContainer {{ background: {c['bg1']}; }}"
            f"QFrame#LocalSingleDrop {{ background: {c['bg0']}; border: 1.5px dashed {c['dash']}; border-radius: 2px; }}"
            f"QFrame#LocalSingleDrop:hover {{ border-color: {c['fg3']}; }}"
        )
        self._gen_slider.setStyleSheet(slider_style)
        self._char_slider.setStyleSheet(slider_style)
        self._drop_zone.apply_theme()
        self._drop_zone.setStyleSheet(
            f"QFrame#LocalSingleDrop {{ background: {c['bg0']}; border: 1.5px dashed {c['dash']}; border-radius: 2px; }}"
            f"QFrame#LocalSingleDrop:hover {{ border-color: {c['fg3']}; }}"
        )
        self._drop_zone._label.setText(
            self._lt("interrogator_drop_image", "拖入图片或点击选择")
            + "\n"
            + self._lt("interr_local_drop_subtitle", "单张 · 选中后自动推理")
        )
        self._drop_zone._label.setStyleSheet(
            f"color: {c['fg3']}; font-size: {_fs('fs_10')}; border: none; line-height: 1.55;"
        )

    def _create_status_row(self, parent, key: str, label: str) -> QWidget:
        c = _local_colors()
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(_dp(12), _dp(9), _dp(12), _dp(9))
        layout.setSpacing(_dp(8))
        led = QLabel("●", row)
        led.setFixedWidth(_dp(10))
        layout.addWidget(led)
        name = QLabel(label, row)
        name.setStyleSheet(f"color: {c['fg1']}; font-size: {_fs('fs_9')};")
        layout.addWidget(name)
        layout.addStretch()
        value = QLabel("", row)
        value.setStyleSheet(f"color: {c['fg2']}; font-size: {_fs('fs_9')};")
        layout.addWidget(value)
        row.setStyleSheet(f"border-bottom: 1px solid {c['line']};")
        self._setup_leds[key] = led
        self._setup_status_values[key] = value
        return row

    def _setup_status_word(self, state: str) -> str:
        return {
            "ok": self._lt("interr_local_status_ok", "已就绪"),
            "missing": self._lt("interr_local_status_missing", "未找到"),
            "error": self._lt("interr_local_status_error", "失败"),
            "running": self._lt("interr_local_status_running", "安装中..."),
            "idle": self._lt("interr_local_status_idle", "未检查"),
        }.get(state, "—")

    def _set_led(self, key: str, state: str) -> None:
        c = _local_colors()
        colors = {
            "ok": c["ok"],
            "missing": c["hot"],
            "error": c["hot"],
            "running": c["accent_text"],
            "idle": c["fg3"],
        }
        led = self._setup_leds.get(key)
        value = self._setup_status_values.get(key)
        if led is not None:
            led.setStyleSheet(f"color: {colors.get(state, c['fg3'])}; font-size: {_fs('fs_10')};")
        if value is not None:
            value.setText(self._setup_status_word(state))

    def _set_banner(self, label: QLabel, text: str, *, show: bool) -> None:
        c = _local_colors()
        label.setText(text)
        label.setVisible(show)
        label.setStyleSheet(
            f"background: {c['bg2']}; color: {c['hot']}; border: 1px solid {c['line2']}; "
            f"border-radius: 2px; padding: {_dp(7)}px {_dp(8)}px; font-size: {_fs('fs_9')};"
        )

    def _refresh_setup_view(self) -> None:
        if not hasattr(self, "_setup_status"):
            return
        model_ok = bool(self._engine and self._engine._model_path)
        direct_ort_ok = bool(model_ok and self._engine and not self._engine._use_subprocess)
        python_ok = bool(direct_ort_ok or self._external_python)
        can_infer = self._can_infer()

        self._setup_model_path.setText(
            os.path.dirname(self._engine._model_path)
            if model_ok and self._engine and self._engine._model_path
            else self._lt("interr_local_model_empty", "未选择模型目录...")
        )
        self._setup_python_path.setText(
            self._external_python or self._lt("interr_local_python_empty", "手动指定 python.exe ...")
        )

        model_state = "ok" if model_ok else "missing"
        ort_state = "running" if self._installing_env else ("ok" if direct_ort_ok else ("missing" if model_ok else "idle"))
        py_state = "running" if self._installing_env else ("ok" if python_ok else ("missing" if model_ok else "idle"))
        if self._last_error_text:
            if not model_ok:
                model_state = "error"
            elif not python_ok:
                py_state = "error"

        self._set_led("model", model_state)
        self._set_led("ort", ort_state)
        self._set_led("python", py_state)

        self._style_local_step(self._setup_model_step, "done" if model_ok else ("error" if self._last_error_text and not model_ok else "active"))
        self._style_local_step(self._setup_python_step, "done" if python_ok else ("active" if model_ok else "idle"))
        self._style_local_step(self._setup_ready_step, "done" if can_infer else "idle")

        status_lines = []
        status_lines.append(self._t.t("interr_model_loaded") if model_ok else self._t.t("interr_please_select_dir"))
        if direct_ort_ok:
            status_lines.append(self._t.t("interr_onnx_available"))
        elif self._external_python:
            status_lines.append(self._t.t("interr_python_configured"))
        else:
            status_lines.append(self._t.t("interr_please_config_python"))
        if self._installing_env:
            if not self._setup_status.text():
                self._setup_status.setText(self._t.t("interr_configuring"))
        elif self._last_error_text:
            self._setup_status.setText(self._last_error_text)
        else:
            self._setup_status.setText("\n".join(status_lines))

        self._start_ready_btn.setVisible(can_infer)
        self._setup_progress.setVisible(self._installing_env)
        if hasattr(self, "_auto_setup_btn"):
            self._auto_setup_btn.setEnabled(not self._installing_env)
            if not self._installing_env and self._auto_setup_btn.text() == self._t.t("interr_configuring"):
                self._auto_setup_btn.setText(self._t.t("interr_auto_setup"))

        model_error = self._last_error_text if self._last_error_text and not model_ok else ""
        python_error = self._last_error_text if self._last_error_text and model_ok and not python_ok else ""
        self._set_banner(self._setup_model_error, model_error, show=bool(model_error))
        self._set_banner(self._setup_python_error, python_error, show=bool(python_error))

    def _clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _select_local_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self._t.t("interrogator_select_image"), "", image_filter(self._t, include_gif=True)
        )
        if path:
            self.load_image(path)

    def load_image(self, path: str) -> None:
        if not path or QPixmap(path).isNull():
            return
        self._drop_zone._set_image(path)

    def _refresh_ready_status(self) -> None:
        if not hasattr(self, "_status"):
            return
        c = _local_colors()
        running = bool(self._worker and self._worker.isRunning())
        has_error = bool(self._last_error_text)
        if running:
            dot_color = c["accent_text"]
            status_text = self._t.t("interr_inferring")
        elif has_error:
            dot_color = c["hot"]
            status_text = self._t.t("interr_infer_failed")
        elif self._last_results:
            dot_color = c["ok"]
            status_text = self._lt("interr_local_infer_done", "推理完成")
        elif self._image_path:
            dot_color = c["fg2"]
            status_text = self._lt("interr_local_waiting_result", "等待推理结果")
        else:
            dot_color = c["fg3"]
            status_text = self._lt("interr_select_image_to_start", "选择一张图片以开始推理")
        self._local_run_dot.setStyleSheet(f"color: {dot_color}; font-size: {_fs('fs_10')};")
        self._status.setText(status_text)

        model_dir = ""
        if self._engine and self._engine._model_path:
            model_dir = os.path.dirname(self._engine._model_path)
        self._path_display.setText(model_dir or self._custom_model_dir or self._lt("interr_local_model_empty", "未选择模型目录..."))

        total = sum(len(v) for v in (self._last_results or {}).values())
        self._footer_status.setText(
            self._lt("interr_local_output_count", "已输出 {count} 个标签").replace("{count}", str(total))
            if total else ""
        )
        self._copy_btn.setEnabled(bool(self._all_tags_str))
        self._send_btn.setEnabled(bool(self._all_tags_str))

    def _make_error_banner(self, text: str, parent) -> QFrame:
        c = _local_colors()
        frame = QFrame(parent)
        frame.setStyleSheet(
            f"background: {c['bg2']}; border: 1px solid {c['line2']}; border-radius: 2px;"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(8))
        layout.setSpacing(_dp(8))
        glyph = QLabel("!", frame)
        glyph.setFixedWidth(_dp(12))
        glyph.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        glyph.setStyleSheet(f"color: {c['hot']}; font-size: {_fs('fs_11')}; font-weight: bold;")
        layout.addWidget(glyph)
        msg = QLabel(text, frame)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color: {c['fg1']}; font-size: {_fs('fs_10')};")
        layout.addWidget(msg, 1)
        return frame

    def _add_result_group(self, category: str, entries: list[tuple[str, float]]) -> None:
        c = _local_colors()
        group = QFrame(self._result_container)
        group.setStyleSheet(f"QFrame {{ border-top: 1px solid {c['line']}; background: transparent; }}")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(8))
        layout.setSpacing(_dp(7))

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        swatch = QLabel(group)
        swatch.setFixedSize(_dp(6), _dp(6))
        swatch.setStyleSheet(f"background: {_semantic_category_color(category)}; border-radius: 1px;")
        head.addWidget(swatch)
        name = QLabel(_local_category_label(self._t, category), group)
        name.setStyleSheet(f"color: {c['fg1']}; font-size: {_fs('fs_9')}; font-weight: bold; letter-spacing: 0.08em;")
        head.addWidget(name)
        count = QLabel(str(len(entries)), group)
        count.setStyleSheet(f"color: {c['fg3']}; font-size: {_fs('fs_9')};")
        head.addWidget(count)
        head.addStretch()
        layout.addLayout(head)

        body = QWidget(group)
        flow = _FlowLayout(body, spacing=_dp(4))
        flow.setContentsMargins(0, 0, 0, 0)
        if entries:
            for tag, prob in entries:
                display_name, category_id, translation, semantic_category = self._local_tag_meta(tag, category)
                flow.addWidget(_LocalTagChip(
                    display_name,
                    category,
                    prob,
                    self._show_conf,
                    category_id=category_id,
                    semantic_category=semantic_category,
                    translation=translation,
                    translator=self._t,
                    parent=body,
                ))
        else:
            empty = QLabel("—", body)
            empty.setStyleSheet(f"color: {c['fg3']}; font-size: {_fs('fs_10')}; font-style: italic;")
            flow.addWidget(empty)
        layout.addWidget(body)
        self._result_layout.addWidget(group)

    def _local_tag_meta(self, tag: str, fallback_category: str) -> tuple[str, int | None, str, str]:
        dictionary = getattr(self, "_tag_dict", None)
        semantic_category = _LOCAL_CATEGORY_SEMANTIC.get(fallback_category, "quality")
        if dictionary is not None:
            info = dictionary.lookup(tag)
            if info is not None:
                return (
                    info.name,
                    info.category_id,
                    info.translation,
                    _semantic_category_for_tag(info, info.name, fallback_category),
                )
        category_to_id = {
            "general": 0,
            "artist": 1,
            "copyright": 3,
            "character": 4,
            "meta": 5,
        }
        return tag, category_to_id.get(fallback_category), "", semantic_category

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
        self._last_error_text = ""
        self._update_setup_status()

    def _browse_python(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._t.t("interr_select_python"), "",
            python_filter(self._t)
        )
        if not path:
            return
        self._external_python = path
        self._last_error_text = ""
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
        self._installing_env = True
        self._last_error_text = ""
        if hasattr(self, '_auto_setup_btn'):
            self._auto_setup_btn.setEnabled(False)
            self._auto_setup_btn.setText(self._t.t("interr_configuring"))
        self._setup_progress.show()
        self._setup_progress.setValue(0)
        self._setup_status.setText("")
        self._refresh_setup_view()

        self._env_worker = PythonEnvSetupWorker(self)
        self._env_worker.progress.connect(self._on_env_setup_progress)
        self._env_worker.finished.connect(self._on_env_setup_done)
        self._env_worker.error.connect(self._on_env_setup_error)
        self._env_worker.start()

    def _on_env_setup_progress(self, message: str, percent: int):
        self._setup_status.setText(message)
        self._setup_progress.setValue(percent)
        self._refresh_setup_view()

    def _on_env_setup_done(self, python_path: str):
        self._installing_env = False
        self._last_error_text = ""
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
        self._installing_env = False
        self._last_error_text = self._t.t("interr_config_failed").format(error=error)
        self._setup_progress.hide()
        self._setup_status.setText(self._last_error_text)
        if hasattr(self, '_auto_setup_btn'):
            self._auto_setup_btn.setEnabled(True)
            self._auto_setup_btn.setText(self._t.t("interr_auto_setup"))
        self._refresh_setup_view()

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
                self._refresh_setup_view()
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
            self._last_error_text = ""
            self._refresh_setup_view()

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
        self._refresh_setup_view()
        self._refresh_ready_status()

    def set_mode(self, index: int) -> None:
        for attr in ("_setup_mode_switch", "_ready_mode_switch"):
            switch = getattr(self, attr, None)
            if switch is not None:
                switch.set_mode(index)

    def apply_theme(self) -> None:
        self._rebuild_pages()

    def retranslate_ui(self) -> None:
        for attr in ("_setup_mode_switch", "_ready_mode_switch"):
            switch = getattr(self, attr, None)
            if switch is not None:
                switch.retranslate_ui()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_category_wrap_height()
        if getattr(self, "_stack", None) is not None and self._stack.currentIndex() == 1:
            self._apply_local_splitter_ratio()

    def _refresh_category_wrap_height(self) -> None:
        wrap = getattr(self, "_category_wrap", None)
        buttons = getattr(self, "_cat_buttons", None)
        if wrap is None or not buttons:
            return
        available = max(1, wrap.width())
        spacing = _dp(6)
        line_count = 1
        used = 0
        for btn in buttons.values():
            width = btn.width() if btn.width() > 0 else max(btn.minimumWidth(), btn.sizeHint().width())
            next_used = width if used == 0 else used + spacing + width
            if next_used > available and used > 0:
                line_count += 1
                used = width
            else:
                used = next_used
        height = min(_dp(46), line_count * _dp(20) + (line_count - 1) * spacing)
        if wrap.minimumHeight() != height:
            wrap.setMinimumHeight(height)
            wrap.setMaximumHeight(height)
            wrap.updateGeometry()

    def _switch_to_ready(self, model_dir: str):
        self._stack.setCurrentIndex(1)
        self._path_display.setText(model_dir)
        self._status.setText(self._t.t("interr_model_loaded"))
        self._last_error_text = ""
        self._refresh_ready_status()

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
        self._refresh_setup_view()

    def _browse_model_dir(self):
        path = QFileDialog.getExistingDirectory(self, self._t.t("interr_select_model_dir_dialog"))
        if not path:
            return
        self._custom_model_dir = path
        self._last_error_text = ""
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
                self._last_error_text = self._t.t("interr_load_failed").format(error=e)
                self._setup_status.setText(self._last_error_text)
                self._refresh_setup_view()
        else:
            self._last_error_text = self._t.t("interr_no_model_found")
            self._setup_status.setText(self._last_error_text)
            self._refresh_setup_view()

    # ───────────────── Inference ─────────────────

    def _toggle_category(self, cat: str):
        if cat in self._enabled_categories:
            self._enabled_categories.discard(cat)
        else:
            self._enabled_categories.add(cat)
        self._apply_cat_styles()
        self._render_results()
        if not self._populating_settings:
            self.settings_changed.emit()

    def _on_local_threshold_changed(self, kind: str, label: QLabel, value: int) -> None:
        if kind == "general":
            self._local_general_threshold = value
        else:
            self._local_character_threshold = value
        label.setText(f"{value/100:.2f}")
        if not self._populating_settings:
            self.settings_changed.emit()

    def _apply_local_splitter_ratio(self) -> None:
        splitter = getattr(self, "_local_splitter", None)
        if splitter is None:
            return
        total = max(_dp(520), splitter.width())
        min_preview = _dp(130)
        min_results = _dp(220)
        preview = max(min_preview, min(total - min_results, int(total * self._local_preview_ratio / 100)))
        results = max(min_results, total - preview)
        self._populating_settings = True
        splitter.setSizes([preview, results])
        self._populating_settings = False

    def _on_local_splitter_moved(self, *_args) -> None:
        if self._populating_settings:
            return
        splitter = getattr(self, "_local_splitter", None)
        if splitter is None:
            return
        sizes = splitter.sizes()
        if len(sizes) != 2:
            return
        total = max(1, sum(sizes))
        self._local_preview_ratio = max(12, min(70, round(sizes[0] * 100 / total)))
        self.settings_changed.emit()

    def _apply_cat_styles(self):
        p = _local_colors()
        for cat, btn in self._cat_buttons.items():
            if cat in self._enabled_categories:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {p['bg3']}; color: {p['fg0']}; "
                    f"border: 1px solid {p['line2']}; border-radius: 2px; padding: 0px 8px; "
                    f"font-size: {_fs('fs_9')}; font-weight: bold; letter-spacing: 0.04em; text-align: left; }}"
                    f"QPushButton:hover {{ color: {p['fg0']}; border-color: {p['fg2']}; }}"
                )
                btn.setText(cat)
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {p['fg3']}; "
                    f"border: 1px solid transparent; border-radius: 2px; padding: 0px 8px; "
                    f"font-size: {_fs('fs_9')}; font-weight: bold; letter-spacing: 0.04em; text-align: left; }}"
                    f"QPushButton:hover {{ color: {p['fg1']}; border-color: {p['line']}; }}"
                )
                btn.setText(cat)

    def _on_image_selected(self, path: str):
        self._image_path = path
        self._last_error_text = ""
        self._last_results = None
        self._all_tags_str = ""
        self._refresh_ready_status()
        if self._engine and self._engine.is_ready:
            self._run_inference()

    def _run_inference(self):
        if not self._image_path or not self._engine or not self._engine.is_ready:
            return
        from ..tagger import TaggerWorker
        self._last_error_text = ""
        self._last_results = None
        self._all_tags_str = ""
        self._status.setText(self._t.t("interr_inferring"))
        self._clear_layout(self._result_layout)
        loading = QLabel(self._t.t("interr_inferring"), self._result_container)
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setStyleSheet(f"color: {_local_colors()['fg2']}; font-size: {_fs('fs_10')}; padding: {_dp(24)}px;")
        self._result_layout.addWidget(loading, 1)
        self._refresh_ready_status()
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
        self._last_error_text = error
        self._last_results = None
        self._all_tags_str = ""
        self._status.setText(self._t.t("interr_infer_failed"))
        self._clear_layout(self._result_layout)
        box = QWidget(self._result_container)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(_dp(12), _dp(12), _dp(12), _dp(12))
        box_layout.setSpacing(_dp(8))
        box_layout.addWidget(self._make_error_banner(error, box))
        back_btn = QPushButton(self._t.t("interr_back_to_setup"), box)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(_local_button_style())
        back_btn.clicked.connect(lambda: (self._stack.setCurrentIndex(0), self._update_setup_status()))
        box_layout.addWidget(back_btn, 0, Qt.AlignmentFlag.AlignLeft)
        box_layout.addStretch()
        self._result_layout.addWidget(box, 1)
        self._refresh_ready_status()

    def _on_inference_done(self, results: dict):
        self._last_results = self._normalize_local_results(results)
        self._last_error_text = ""
        total = sum(len(v) for v in self._last_results.values())
        self._status.setText(self._t.t("local_tags_count").format(count=total))
        self._render_results()
        self._refresh_ready_status()

    def _normalize_local_results(self, results: dict) -> dict:
        if not isinstance(results, dict):
            return {}
        from ..tagger import CATEGORY_NAMES
        known = set(CATEGORY_NAMES)
        normalized: dict[str, list[tuple[str, float]]] = {cat: [] for cat in CATEGORY_NAMES}
        for category, entries in results.items():
            if isinstance(entries, (list, tuple)) and entries and isinstance(entries[0], (list, tuple)):
                target = category if category in known else "general"
                normalized.setdefault(target, [])
                normalized[target].extend((str(name), float(prob)) for name, prob in entries)
                continue
            if isinstance(entries, (int, float)):
                target = category if category in known else "general"
                normalized.setdefault(target, []).append((str(category), float(entries)))
        return {cat: vals for cat, vals in normalized.items() if vals}

    def _render_results(self):
        """Render results with or without confidence scores."""
        results = getattr(self, '_last_results', None)
        if not hasattr(self, "_result_layout"):
            return
        self._clear_layout(self._result_layout)
        if not results:
            label = QLabel(self._lt("interr_select_image_to_start", "选择一张图片以开始推理"), self._result_container)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(f"color: {_local_colors()['fg3']}; font-size: {_fs('fs_10')}; padding: {_dp(24)}px;")
            self._result_layout.addWidget(label, 1)
            self._all_tags_str = ""
            self._refresh_ready_status()
            return
        all_tags = []
        from ..tagger import CATEGORY_NAMES
        active_categories = set(self._enabled_categories) | set(results.keys())
        for category in CATEGORY_NAMES:
            if category not in active_categories:
                continue
            entries = list(results.get(category, [])) if category in self._enabled_categories else []
            self._add_result_group(category, entries)
            all_tags.extend(name for name, _ in entries)
        self._result_layout.addStretch()
        self._all_tags_str = ", ".join(all_tags)
        self._refresh_ready_status()

    def _toggle_confidence(self):
        self._show_conf = not self._show_conf
        p = current_palette()
        if self._show_conf:
            self._conf_btn.setText(self._t.t("interr_hide_conf"))
        else:
            self._conf_btn.setText(self._t.t("interr_show_conf"))
        self._conf_btn.setStyleSheet(_local_button_style())
        self._render_results()
        if not self._populating_settings:
            self.settings_changed.emit()

    def _copy_result(self):
        if self._all_tags_str:
            QApplication.clipboard().setText(self._all_tags_str)

    def _send_result(self):
        text = self._all_tags_str
        if text:
            self.send_to_input.emit(text)


# ═══════════════════════════════════════════════════
#  Flow Layout (for tag display)
# ═══════════════════════════════════════════════════

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

_LLM_DENSITY = {
    "compact": {"pad": 6, "tag_h": 20, "tag_px": 6, "thumb_row_extra": 12, "footer_v": 6},
    "comfortable": {"pad": 8, "tag_h": 22, "tag_px": 8, "thumb_row_extra": 14, "footer_v": 8},
    "spacious": {"pad": 11, "tag_h": 26, "tag_px": 10, "thumb_row_extra": 18, "footer_v": 10},
}


def _llm_density(name: str) -> dict[str, int]:
    return _LLM_DENSITY.get(name, _LLM_DENSITY["comfortable"])


def _llm_colors() -> dict[str, str]:
    p = current_palette()
    return {
        "bg0": p["bg_input"],
        "bg1": p["bg_content"],
        "bg2": p["bg_surface"],
        "bg3": p["hover_bg_strong"],
        "line": p["line"],
        "line2": p["line_strong"],
        "dash": p["line_hover"],
        "fg0": p["text"],
        "fg1": p["text_body"],
        "fg2": p["text_muted"],
        "fg3": p["text_dim"],
        "accent": p["accent"],
        "accent_hover": p["accent_hover"],
        "accent_text": p["accent_text"],
        "hot": p["close_hover"],
        "ok": p["accent_text_hover"],
        "warn": p["accent_handle"],
        "selection_text": p["selection_text"],
        "overlay": p["bg_menu"],
        "overlay_hover": p["bg_card_strip_hover"],
        "overlay_text": p["text"],
        "overlay_muted": p["text_muted"],
    }


def _llm_category_color(category_id: int) -> str:
    return _danbooru_category_color(category_id)


def _readable_text_for_hex(bg: str) -> str:
    """Pick readable text for semantic tag colors without tying the UI to a theme."""
    value = bg.lstrip("#")
    if len(value) != 6:
        return current_palette().get("selection_text", "#ffffff")
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return current_palette().get("selection_text", "#ffffff")
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    return "#111111" if luminance > 160 else "#ffffff"


class _InterrogatorModeSwitch(QFrame):
    mode_changed = pyqtSignal(int)

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self._t = translator
        self.setObjectName("InterrogatorModeSwitch")
        self.setFixedHeight(_dp(26))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(_dp(1), _dp(1), _dp(1), _dp(1))
        layout.setSpacing(0)
        self._local_btn = QPushButton(self)
        self._local_btn.setCheckable(True)
        self._local_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._local_btn.clicked.connect(lambda: self.mode_changed.emit(0))
        self._llm_btn = QPushButton(self)
        self._llm_btn.setCheckable(True)
        self._llm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._llm_btn.clicked.connect(lambda: self.mode_changed.emit(1))
        for btn in (self._local_btn, self._llm_btn):
            btn.setFixedHeight(_dp(24))
            btn.setMinimumWidth(_dp(72))
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            layout.addWidget(btn)
        self.retranslate_ui()
        self.set_mode(1)

    def set_mode(self, index: int) -> None:
        index = 1 if index == 1 else 0
        self._local_btn.setChecked(index == 0)
        self._llm_btn.setChecked(index == 1)
        self.apply_theme()

    def retranslate_ui(self) -> None:
        self._local_btn.setText(self._t.t("interrogator_local"))
        self._llm_btn.setText(self._t.t("interrogator_llm"))
        self.apply_theme()

    def apply_theme(self) -> None:
        c = _llm_colors()
        self.setStyleSheet(
            f"QFrame#InterrogatorModeSwitch {{ background: {c['bg0']}; border: 1px solid {c['line2']}; border-radius: 2px; }}"
        )
        for btn in (self._local_btn, self._llm_btn):
            active = btn.isChecked()
            btn.setStyleSheet(
                f"QPushButton {{ background: {c['accent'] if active else 'transparent'}; "
                f"color: {c['accent_text'] if active else c['fg2']}; border: none; border-radius: 0px; "
                f"padding: 2px 10px; font-size: {_fs('fs_10')}; }}"
                f"QPushButton:hover {{ background: {c['accent_hover'] if active else c['bg3']}; "
                f"color: {c['accent_text'] if active else c['fg0']}; }}"
            )


class _LLMTagChip(QPushButton):
    toggled_manual = pyqtSignal(int)

    def __init__(self, index: int, parsed_tag, translator: Translator, *, effective_valid: bool,
                 tag_height: int = 22, tag_padding: int = 8, parent=None):
        super().__init__(parent)
        self._index = index
        self._tag = parsed_tag
        self._t = translator
        self._effective_valid = effective_valid
        self._tag_height = tag_height
        self._tag_padding = tag_padding
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.clicked.connect(lambda: self.toggled_manual.emit(self._index))
        self.refresh()

    def refresh(self) -> None:
        c = _llm_colors()
        self.setText(self._tag.name)
        self.setFixedHeight(_dp(self._tag_height))
        self.setMinimumWidth(_dp(28))
        self.setToolTip(
            self._tag.translation
            if self._effective_valid and self._tag.translation
            else self._t.t("llm_tagger_click_disable" if self._effective_valid else "llm_tagger_click_restore")
        )
        if self._effective_valid:
            bg = _llm_category_color(self._tag.category_id)
            fg = _readable_text_for_hex(bg)
            self.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {fg}; border: none; "
                f"border-radius: 2px; padding: 0px {_dp(self._tag_padding)}px; "
                f"font-size: {_fs('fs_10')}; letter-spacing: 0px; }}"
                f"QPushButton:hover {{ border: 1px solid {c['line2']}; }}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {c['fg3']}; "
                f"border: 1px dashed {c['line2']}; border-radius: 2px; "
                f"padding: 0px {_dp(self._tag_padding)}px; font-size: {_fs('fs_10')}; font-style: italic; "
                f"text-decoration: line-through; }}"
                f"QPushButton:hover {{ color: {c['fg1']}; border-color: {c['fg2']}; }}"
            )


class _LLMThumbButton(QFrame):
    selected = pyqtSignal(int)
    remove_requested = pyqtSignal(int)

    def __init__(self, index: int, path: str, *, thumb_width: int = 38, thumb_height: int = 38, parent=None):
        super().__init__(parent)
        self._index = index
        self._path = path
        self._thumb_width = thumb_width
        self._thumb_height = thumb_height
        self.setFixedSize(_dp(thumb_width + 2), _dp(thumb_height + 6))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(os.path.basename(path))

        self._thumb = QLabel(self)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setGeometry(_dp(1), _dp(1), _dp(thumb_width), _dp(thumb_height))
        pix = QPixmap(path)
        if not pix.isNull():
            self._thumb.setPixmap(pix.scaled(
                _dp(max(12, thumb_width - 3)), _dp(max(12, thumb_height - 3)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

        self._remove_btn = QPushButton("×", self)
        self._remove_btn.setFixedSize(_dp(14), _dp(14))
        self._remove_btn.move(self.width() - _dp(14), 0)
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._index))
        self._active_dot = QLabel(self)
        self._active_dot.setFixedSize(_dp(4), _dp(4))
        self._active_dot.move(max(0, (self.width() - self._active_dot.width()) // 2), self.height() - _dp(4))
        self.apply_theme()
        self.set_selected(False)

    def set_index(self, index: int) -> None:
        self._index = index

    def set_selected(self, selected: bool) -> None:
        c = _llm_colors()
        border = c["fg0"] if selected else c["line2"]
        width = 2 if selected else 1
        self.setStyleSheet(
            f"QFrame {{ background: {c['bg3']}; border: {width}px solid {border}; "
            f"border-radius: 2px; }}"
        )
        self._active_dot.setVisible(selected)

    def apply_theme(self) -> None:
        c = _llm_colors()
        self._remove_btn.setStyleSheet(
            f"QPushButton {{ background: {c['bg3']}; color: {c['fg2']}; "
            f"border: 1px solid {c['line']}; border-radius: 0px; padding: 0px; "
            f"font-size: {_fs('fs_8')}; }}"
            f"QPushButton:hover {{ color: {c['hot']}; border-color: {c['hot']}; }}"
        )
        self._active_dot.setStyleSheet(f"background: {c['fg0']}; border-radius: 2px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._index)
            return
        super().mousePressEvent(event)


class _LLMPreviewPanel(QFrame):
    previous_requested = pyqtSignal()
    next_requested = pyqtSignal()

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self._t = translator
        self._path = ""
        self._pixmap = QPixmap()
        self.setMinimumHeight(_dp(190))
        self.setObjectName("LLMPreviewPanel")

        self._image = QLabel(self)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setScaledContents(False)

        self._prev_btn = QPushButton("‹", self)
        self._next_btn = QPushButton("›", self)
        for btn in (self._prev_btn, self._next_btn):
            btn.setFixedSize(_dp(28), _dp(28))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self.previous_requested.emit)
        self._next_btn.clicked.connect(self.next_requested.emit)

        self._info_bar = QWidget(self)
        self._info_bar.setObjectName("LLMPreviewInfo")
        info = QHBoxLayout(self._info_bar)
        info.setContentsMargins(_dp(10), 0, _dp(10), 0)
        info.setSpacing(_dp(8))
        self._name_label = QLabel("", self._info_bar)
        self._name_label.setMinimumWidth(_dp(80))
        self._index_label = QLabel("", self._info_bar)
        self._valid_label = QLabel("", self._info_bar)
        self._invalid_label = QLabel("", self._info_bar)
        info.addWidget(self._name_label, 1)
        info.addWidget(self._index_label)
        info.addStretch()
        info.addWidget(self._valid_label)
        info.addWidget(self._invalid_label)
        self.apply_theme()

    def set_image(self, path: str, index_text: str, valid_count: int, invalid_count: int) -> None:
        self._path = path
        self._pixmap = QPixmap(path) if path else QPixmap()
        self._name_label.setText(os.path.basename(path) if path else self._t.t("llm_tagger_waiting"))
        self._index_label.setText(index_text)
        self._valid_label.setText(f"{valid_count} {self._t.t('llm_tagger_valid_short')}")
        self._invalid_label.setText(f"· {invalid_count} {self._t.t('llm_tagger_invalid_short')}")
        self._rescale()

    def apply_theme(self) -> None:
        c = _llm_colors()
        self.setStyleSheet(
            f"QFrame#LLMPreviewPanel {{ background: {c['bg0']}; border-bottom: 1px solid {c['line']}; }}"
            f"QWidget#LLMPreviewInfo {{ background: {c['overlay']}; }}"
        )
        self._name_label.setStyleSheet(f"color: {c['overlay_text']}; font-size: {_fs('fs_10')};")
        self._index_label.setStyleSheet(f"color: {c['overlay_muted']}; font-size: {_fs('fs_9')};")
        self._valid_label.setStyleSheet(f"color: {c['ok']}; font-size: {_fs('fs_9')};")
        self._invalid_label.setStyleSheet(f"color: {c['overlay_muted']}; font-size: {_fs('fs_9')};")
        nav_style = (
            f"QPushButton {{ background: {c['overlay']}; color: {c['overlay_text']}; "
            f"border: 1px solid {c['line2']}; border-radius: 0px; padding: 0px; }}"
            f"QPushButton:hover {{ background: {c['overlay_hover']}; }}"
        )
        self._prev_btn.setStyleSheet(nav_style)
        self._next_btn.setStyleSheet(nav_style)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._image.setGeometry(0, 0, self.width(), self.height())
        self._info_bar.setGeometry(0, max(0, self.height() - _dp(30)), self.width(), _dp(30))
        center_y = max(0, (self.height() - self._prev_btn.height()) // 2)
        self._prev_btn.move(_dp(8), center_y)
        self._next_btn.move(max(_dp(8), self.width() - self._next_btn.width() - _dp(8)), center_y)
        self._rescale()

    def _rescale(self) -> None:
        if self._pixmap.isNull():
            self._image.clear()
            self._image.setText(self._t.t("llm_tagger_waiting"))
            self._image.setStyleSheet(f"color: {_llm_colors()['fg3']}; font-size: {_fs('fs_10')};")
            return
        self._image.setText("")
        self._image.setStyleSheet("")
        target = self._image.size()
        if target.width() > 2 and target.height() > 2:
            self._image.setPixmap(self._pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))


class _LLMTaggerTab(QWidget):
    """Tab for LLM multimodal image tagging with batch, presets, and tag validation."""

    send_to_input = pyqtSignal(str)
    settings_changed = pyqtSignal()
    mode_changed = pyqtSignal(int)

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
        self._active_index: int = 0
        self._is_running: bool = False
        self._last_error: str = ""
        self._error_by_path: dict[str, str] = {}
        self._manual_invalid: dict[str, set[int]] = {}
        self._manual_valid: dict[str, set[int]] = {}
        self._layout_density: str = "comfortable"
        self._preview_ratio: int = 42
        self._thumb_size: int = 38
        self._tag_density: int = 2
        self._layout_populating: bool = False
        self._portrait_layout: bool = False
        self._max_tokens: int = 4096

        self._api_base_url = ""
        self._api_key = ""
        self._model = ""

        self._build_ui()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top toolbar mirrors the JSX design: preset · edit · stats · start/stop.
        self._top_bar = QWidget(self)
        self._top_bar.setObjectName("LLMTopBar")
        top = QHBoxLayout(self._top_bar)
        top.setContentsMargins(_dp(10), _dp(8), _dp(10), _dp(8))
        top.setSpacing(_dp(8))

        self._mode_switch = _InterrogatorModeSwitch(self._t, self._top_bar)
        self._mode_switch.mode_changed.connect(self.mode_changed.emit)
        top.addWidget(self._mode_switch)

        self._preset_combo = QComboBox(self._top_bar)
        self._preset_combo.setFixedWidth(_dp(130))
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        top.addWidget(self._preset_combo)

        self._edit_btn = QPushButton("✎", self._top_bar)
        self._edit_btn.setObjectName("LLMIconButton")
        self._edit_btn.setCheckable(True)
        self._edit_btn.setFixedSize(_dp(26), _dp(26))
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.clicked.connect(self._toggle_editor)
        top.addWidget(self._edit_btn)

        self._layout_btn = QPushButton("↺", self._top_bar)
        self._layout_btn.setObjectName("LLMIconButton")
        self._layout_btn.setFixedSize(_dp(26), _dp(26))
        self._layout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layout_btn.clicked.connect(self._reset_layout_preferences)
        top.addWidget(self._layout_btn)

        self._stats_label = QLabel("", self._top_bar)
        top.addWidget(self._stats_label, 1)

        self._start_btn = QPushButton(self._t.t("interrogator_start"), self._top_bar)
        self._start_btn.setObjectName("LLMPrimaryButton")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._toggle_run)
        top.addWidget(self._start_btn)
        root.addWidget(self._top_bar)

        # Editor panel is the old preset/API customization, now inline like the design.
        self._edit_panel = QWidget(self)
        self._edit_panel.setObjectName("LLMEditorPanel")
        edit_layout = QVBoxLayout(self._edit_panel)
        edit_layout.setContentsMargins(_dp(12), _dp(10), _dp(12), _dp(10))
        edit_layout.setSpacing(_dp(8))

        edit_row = QHBoxLayout()
        edit_row.setSpacing(_dp(8))
        self._name_edit = QLineEdit(self._edit_panel)
        self._name_edit.setPlaceholderText(self._t.t("llm_tagger_preset_name"))
        self._name_edit.textChanged.connect(self._on_name_edited)
        edit_row.addWidget(self._name_edit, 1)

        self._add_preset_btn = QPushButton("+", self._edit_panel)
        self._add_preset_btn.setObjectName("LLMIconButton")
        self._add_preset_btn.setFixedSize(_dp(26), _dp(26))
        self._add_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_preset_btn.clicked.connect(self._add_preset)
        edit_row.addWidget(self._add_preset_btn)

        self._del_preset_btn = QPushButton("×", self._edit_panel)
        self._del_preset_btn.setObjectName("LLMIconButton")
        self._del_preset_btn.setFixedSize(_dp(26), _dp(26))
        self._del_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_preset_btn.clicked.connect(self._delete_preset)
        edit_row.addWidget(self._del_preset_btn)

        edit_layout.addLayout(edit_row)

        self._prompt_edit = QTextEdit(self._edit_panel)
        self._prompt_edit.setMinimumHeight(_dp(60))
        self._prompt_edit.setMaximumHeight(_dp(96))
        self._prompt_edit.setPlaceholderText(self._t.t("interrogator_llm_prompt"))
        self._prompt_edit.textChanged.connect(self._on_text_edited)
        edit_layout.addWidget(self._prompt_edit)

        self._api_toggle = QPushButton(self._t.t("llm_tagger_use_separate_api"), self._edit_panel)
        self._api_toggle.setObjectName("LLMToggleButton")
        self._api_toggle.setCheckable(True)
        self._api_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._api_toggle.clicked.connect(self._on_api_toggle)
        edit_layout.addWidget(self._api_toggle, 0, Qt.AlignmentFlag.AlignLeft)

        self._api_fields_widget = QWidget(self._edit_panel)
        api_fields = QVBoxLayout(self._api_fields_widget)
        api_fields.setContentsMargins(0, 0, 0, 0)
        api_fields.setSpacing(_dp(6))

        self._separate_url = QLineEdit(self._api_fields_widget)
        self._separate_url.setPlaceholderText(self._t.t("llm_tagger_api_base_url"))
        self._separate_url.textChanged.connect(self._on_api_field_changed)
        api_fields.addWidget(self._separate_url)

        self._separate_key = QLineEdit(self._api_fields_widget)
        self._separate_key.setPlaceholderText(self._t.t("llm_tagger_api_key"))
        self._separate_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._separate_key.textChanged.connect(self._on_api_field_changed)
        api_fields.addWidget(self._separate_key)

        self._separate_model = QLineEdit(self._api_fields_widget)
        self._separate_model.setPlaceholderText(self._t.t("llm_tagger_api_model"))
        self._separate_model.textChanged.connect(self._on_api_field_changed)
        api_fields.addWidget(self._separate_model)

        self._api_fields_widget.hide()
        edit_layout.addWidget(self._api_fields_widget)
        self._edit_panel.hide()
        root.addWidget(self._edit_panel)

        # Status strip.
        self._status_strip = QWidget(self)
        self._status_strip.setObjectName("LLMStatusStrip")
        status = QHBoxLayout(self._status_strip)
        status.setContentsMargins(_dp(12), _dp(6), _dp(12), _dp(6))
        status.setSpacing(_dp(12))
        self._run_dot = QLabel("●", self._status_strip)
        self._status_label = QLabel("", self._status_strip)
        self._progress = QProgressBar(self._status_strip)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setFixedHeight(_dp(2))
        self._valid_total_label = QLabel("", self._status_strip)
        self._error_label = QLabel("", self._status_strip)
        status.addWidget(self._run_dot)
        status.addWidget(self._status_label)
        status.addWidget(self._progress, 1)
        status.addWidget(self._valid_total_label)
        status.addWidget(self._error_label)
        root.addWidget(self._status_strip)

        # Body stack: empty dashed dropzone, or the full workbench.
        self._body_stack = QStackedWidget(self)

        self._drop_zone = _DropZone(self._t, self._body_stack, multi=True)
        self._drop_zone.images_selected.connect(self._on_images_selected)
        self._body_stack.addWidget(self._drop_zone)

        self._workbench = QWidget(self._body_stack)
        work = QVBoxLayout(self._workbench)
        work.setContentsMargins(0, 0, 0, 0)
        work.setSpacing(0)

        self._workbench_splitter = QSplitter(Qt.Orientation.Vertical, self._workbench)
        self._workbench_splitter.setObjectName("LLMWorkbenchSplitter")
        self._workbench_splitter.setChildrenCollapsible(False)
        self._workbench_splitter.splitterMoved.connect(self._on_workbench_splitter_moved)

        self._preview_panel = _LLMPreviewPanel(self._t, self._workbench)
        self._preview_panel.setMinimumHeight(_dp(130))
        self._preview_panel.setMinimumWidth(_dp(160))
        self._preview_panel.previous_requested.connect(self._prev_image)
        self._preview_panel.next_requested.connect(self._next_image)
        self._workbench_splitter.addWidget(self._preview_panel)

        self._tag_scroll = QScrollArea(self._workbench)
        self._tag_scroll.setWidgetResizable(True)
        self._tag_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tag_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tag_scroll.setMinimumHeight(_dp(58))
        self._tag_container = QWidget()
        self._tag_layout = _FlowLayout(self._tag_container, spacing=_dp(4))
        self._tag_layout.setContentsMargins(_dp(10), _dp(10), _dp(10), _dp(10))
        self._tag_scroll.setWidget(self._tag_container)
        self._workbench_splitter.addWidget(self._tag_scroll)
        self._workbench_splitter.setStretchFactor(0, 5)
        self._workbench_splitter.setStretchFactor(1, 3)
        work.addWidget(self._workbench_splitter, 1)

        self._thumb_strip = QScrollArea(self._workbench)
        self._thumb_strip.setObjectName("LLMThumbStrip")
        self._thumb_strip.setWidgetResizable(True)
        self._thumb_strip.setMinimumHeight(_dp(38))
        self._thumb_strip.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._thumb_strip.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._thumb_container = QWidget()
        self._thumb_layout = QHBoxLayout(self._thumb_container)
        self._thumb_layout.setContentsMargins(_dp(10), _dp(6), _dp(10), _dp(6))
        self._thumb_layout.setSpacing(_dp(4))
        self._thumb_strip.setWidget(self._thumb_container)
        work.addWidget(self._thumb_strip)

        self._body_stack.addWidget(self._workbench)
        root.addWidget(self._body_stack, 1)

        footer = QWidget(self)
        footer.setObjectName("LLMFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(_dp(12), _dp(8), _dp(12), _dp(8))
        footer_layout.setSpacing(_dp(8))
        self._copy_current_btn = QPushButton(self._t.t("llm_tagger_copy_current"), footer)
        self._copy_current_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_current_btn.clicked.connect(self._copy_current)
        footer_layout.addWidget(self._copy_current_btn, 1)
        self._copy_all_btn = QPushButton(self._t.t("llm_tagger_copy_all"), footer)
        self._copy_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_all_btn.clicked.connect(self._copy_all)
        footer_layout.addWidget(self._copy_all_btn, 1)
        self._send_all_btn = QPushButton(self._t.t("llm_tagger_send_all"), footer)
        self._send_all_btn.setObjectName("LLMPrimaryButton")
        self._send_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_all_btn.clicked.connect(self._send_all)
        footer_layout.addWidget(self._send_all_btn, 1)
        root.addWidget(footer)

        self._prev_shortcut = QShortcut(QKeySequence("Left"), self)
        self._prev_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._prev_shortcut.activated.connect(self._prev_image_from_shortcut)
        self._next_shortcut = QShortcut(QKeySequence("Right"), self)
        self._next_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._next_shortcut.activated.connect(self._next_image_from_shortcut)

        self._apply_layout_preferences()
        self.apply_theme()
        self._refresh_all()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_layout_preferences()

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
        self._separate_url.setText(getattr(settings, "tagger_llm_base_url", "") or "")
        self._separate_key.setText(getattr(settings, "tagger_llm_api_key", "") or "")
        self._separate_model.setText(getattr(settings, "tagger_llm_model", "") or "")
        self._layout_density = self._normalize_density(getattr(settings, "tagger_llm_layout_density", "comfortable"))
        self._preview_ratio = max(18, min(78, int(getattr(settings, "tagger_llm_preview_ratio", 42) or 42)))
        self._thumb_size = max(28, min(72, int(getattr(settings, "tagger_llm_thumb_size", 38) or 38)))
        self._tag_density = max(1, min(3, int(getattr(settings, "tagger_llm_tag_density", 2) or 2)))
        self._max_tokens = max(1, min(200000, int(getattr(settings, "max_tokens", 4096) or 4096)))
        self._sync_layout_controls()
        self._apply_layout_preferences()
        self._populating = False

    def collect_llm_settings(self) -> dict:
        return {
            "tagger_llm_presets": [dict(p) for p in self._presets],
            "tagger_llm_active_preset": max(0, self._preset_combo.currentIndex()),
            "tagger_llm_use_separate": self._api_toggle.isChecked(),
            "tagger_llm_base_url": self._separate_url.text(),
            "tagger_llm_api_key": self._separate_key.text(),
            "tagger_llm_model": self._separate_model.text(),
            "tagger_llm_layout_density": self._layout_density,
            "tagger_llm_preview_ratio": self._preview_ratio,
            "tagger_llm_thumb_size": self._thumb_size,
            "tagger_llm_tag_density": self._tag_density,
        }

    def set_mode(self, index: int) -> None:
        self._mode_switch.set_mode(index)

    # ── Slots ──

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

    def _toggle_editor(self) -> None:
        self._edit_panel.setVisible(self._edit_btn.isChecked())

    def _normalize_density(self, value: str) -> str:
        return value if value in _LLM_DENSITY else "comfortable"

    def _sync_layout_controls(self) -> None:
        return

    def _on_layout_controls_changed(self, *_args) -> None:
        return

    def _reset_layout_preferences(self) -> None:
        self._layout_density = "comfortable"
        self._preview_ratio = 42
        self._thumb_size = 38
        self._tag_density = 2
        self._apply_layout_preferences()
        self._refresh_all()
        self.settings_changed.emit()

    def _apply_layout_preferences(self) -> None:
        density = _llm_density(self._layout_density)
        portrait = self._current_image_is_portrait()
        self._portrait_layout = portrait
        self._workbench_splitter.setOrientation(Qt.Orientation.Horizontal if portrait else Qt.Orientation.Vertical)
        thumb_h = 38 + density["thumb_row_extra"]
        self._tag_layout.setSpacing(_dp(max(2, self._tag_density + 2)))
        pad = density["pad"]
        self._tag_layout.setContentsMargins(_dp(pad + 2), _dp(pad), _dp(pad + 2), _dp(pad))
        self._thumb_layout.setContentsMargins(_dp(10), _dp(max(4, pad - 2)), _dp(10), _dp(max(4, pad - 2)))
        self._thumb_strip.setFixedHeight(_dp(thumb_h))
        total = (
            max(_dp(360), self._workbench_splitter.width())
            if portrait
            else max(_dp(260), self._workbench_splitter.height())
        )
        if portrait:
            preview = max(_dp(180), min(_dp(280), int(total * self._preview_ratio / 100)))
        else:
            preview = max(_dp(150), min(_dp(260), int(total * self._preview_ratio / 100)))
        tags = max(_dp(90), total - preview)
        self._layout_populating = True
        self._workbench_splitter.setSizes([preview, tags])
        self._layout_populating = False

    def _on_workbench_splitter_moved(self, *_args) -> None:
        if self._layout_populating:
            return
        sizes = self._workbench_splitter.sizes()
        if len(sizes) != 2:
            return
        total = max(1, sum(sizes))
        self._preview_ratio = max(18, min(78, round(sizes[0] * 100 / total)))
        self.settings_changed.emit()

    def _current_image_is_portrait(self) -> bool:
        if not self._image_paths:
            return False
        pixmap = QPixmap(self._image_paths[self._active_index])
        if pixmap.isNull() or pixmap.width() <= 0:
            return False
        return (pixmap.height() / pixmap.width()) > 1.1

    def _prev_image_from_shortcut(self) -> None:
        if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit)):
            return
        self._prev_image()

    def _next_image_from_shortcut(self) -> None:
        if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit)):
            return
        self._next_image()

    def _toggle_run(self) -> None:
        if self._is_running:
            self._stop_batch()
        else:
            self._start_batch()

    def _on_images_selected(self, paths: list[str]):
        valid: list[str] = []
        seen: set[str] = set()
        for path in paths:
            if path and path not in seen and not QPixmap(path).isNull():
                valid.append(path)
                seen.add(path)
        if not valid:
            return

        keep = set(valid)
        self._image_paths = valid
        self._results = [r for r in self._results if r.image_path in keep]
        self._error_by_path = {k: v for k, v in self._error_by_path.items() if k in keep}
        self._manual_invalid = {k: v for k, v in self._manual_invalid.items() if k in keep}
        self._manual_valid = {k: v for k, v in self._manual_valid.items() if k in keep}
        self._active_index = min(self._active_index, len(self._image_paths) - 1)
        self._refresh_all()

    def load_images(self, paths: list[str]) -> None:
        self._on_images_selected(paths)

    def _add_images_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, self._t.t("interrogator_select_image"), "", image_filter(self._t, include_gif=True)
        )
        if not paths:
            return
        merged = list(self._image_paths)
        for path in paths:
            if path not in merged:
                merged.append(path)
        self._on_images_selected(merged)

    def _remove_image(self, index: int) -> None:
        if self._is_running or not (0 <= index < len(self._image_paths)):
            return
        path = self._image_paths.pop(index)
        self._results = [r for r in self._results if r.image_path != path]
        self._error_by_path.pop(path, None)
        self._manual_invalid.pop(path, None)
        self._manual_valid.pop(path, None)
        self._active_index = min(max(0, self._active_index), max(0, len(self._image_paths) - 1))
        self._refresh_all()

    def _set_active_index(self, index: int) -> None:
        if not self._image_paths:
            return
        self._active_index = index % len(self._image_paths)
        self._refresh_all()

    def _prev_image(self) -> None:
        self._set_active_index(self._active_index - 1)

    def _next_image(self) -> None:
        self._set_active_index(self._active_index + 1)

    def _start_batch(self):
        if not self._image_paths:
            self._last_error = self._t.t("interrogator_no_image")
            self._refresh_status()
            return
        base_url, api_key, model = self._get_effective_api()
        if not base_url or not api_key or not model:
            self._last_error = self._t.t("llm_tagger_no_api")
            self._refresh_status()
            return

        self._results.clear()
        self._current_index = 0
        self._is_running = True
        self._last_error = ""
        self._error_by_path.clear()
        self._manual_invalid.clear()
        self._manual_valid.clear()
        self._active_index = 0
        self._refresh_all()
        self._process_next()

    def _process_next(self):
        if self._current_index >= len(self._image_paths):
            self._on_batch_finished()
            return

        path = self._image_paths[self._current_index]
        self._active_index = self._current_index
        self._raw_buffer = ""
        self._refresh_all()

        from ..llm_tagger_logic import build_vision_messages
        from ..api_client import ChatWorker
        from ..logic import normalize_api_base_url

        base_url, api_key, model = self._get_effective_api()
        messages = build_vision_messages(path, self._get_prompt_text())
        url = f"{normalize_api_base_url(base_url)}/chat/completions"
        payload = {"model": model, "messages": messages, "max_tokens": self._max_tokens, "stream": True}

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

        self._current_index += 1
        self._refresh_all()
        self._process_next()

    def _on_error(self, message: str, status_code: int, details: str):
        from ..models import LLMTagResult

        path = self._image_paths[self._current_index]
        summary = message or details or f"HTTP {status_code}"
        result = LLMTagResult(image_path=path, raw_text=f"{self._t.t('error_prefix')} {summary}")
        self._results.append(result)
        self._error_by_path[path] = summary
        self._last_error = summary

        self._current_index += 1
        self._refresh_all()
        self._process_next()

    def _stop_batch(self):
        if self._worker:
            self._worker.cancel()
        self._current_index = len(self._image_paths)
        self._on_batch_finished()

    def _on_batch_finished(self):
        self._is_running = False
        self._worker = None
        self._refresh_all()

    # ── Workbench rendering ──

    def _refresh_all(self) -> None:
        self._body_stack.setCurrentIndex(1 if self._image_paths else 0)
        self._apply_layout_preferences()
        self._refresh_toolbar()
        self._refresh_status()
        self._refresh_preview()
        self._refresh_tags()
        self._refresh_thumbs()

    def _refresh_toolbar(self) -> None:
        total_valid = self._total_valid_count()
        self._stats_label.setText(
            self._t.t("llm_tagger_toolbar_stats")
            .replace("{images}", str(len(self._image_paths)))
            .replace("{tags}", str(total_valid))
        )
        self._start_btn.setText(self._t.t("llm_tagger_stop") if self._is_running else self._t.t("llm_tagger_start"))
        self._start_btn.setObjectName("LLMDangerButton" if self._is_running else "LLMPrimaryButton")
        self._start_btn.style().unpolish(self._start_btn)
        self._start_btn.style().polish(self._start_btn)

    def _refresh_status(self) -> None:
        c = _llm_colors()
        total = len(self._image_paths)
        done = len(self._results)
        if self._is_running:
            current = min(self._current_index + 1, total)
            text = self._t.t("llm_tagger_batch_progress").replace("{current}", str(current)).replace("{total}", str(total))
            self._run_dot.setStyleSheet(f"color: {c['ok']}; font-size: {_fs('fs_8')};")
            self._status_label.setStyleSheet(f"color: {c['fg0']}; font-size: {_fs('fs_9')};")
        elif total > 0 and done > 0:
            text = self._t.t("llm_tagger_done").replace("{current}", str(done)).replace("{total}", str(total))
            self._run_dot.setStyleSheet(f"color: {c['fg3']}; font-size: {_fs('fs_8')};")
            self._status_label.setStyleSheet(f"color: {c['fg2']}; font-size: {_fs('fs_9')};")
        else:
            text = self._t.t("llm_tagger_idle")
            self._run_dot.setStyleSheet(f"color: {c['fg3']}; font-size: {_fs('fs_8')};")
            self._status_label.setStyleSheet(f"color: {c['fg2']}; font-size: {_fs('fs_9')};")
        self._status_label.setText(text)
        self._progress.setValue(0 if total == 0 else int(done / total * 100))
        self._valid_total_label.setText(
            self._t.t("llm_tagger_valid_tags").replace("{count}", str(self._total_valid_count()))
        )
        self._error_label.setText(f"· {self._last_error}" if self._last_error else "")

    def _refresh_preview(self) -> None:
        if not self._image_paths:
            self._preview_panel.set_image("", "", 0, 0)
            return
        path = self._image_paths[self._active_index]
        result = self._result_for_path(path)
        valid, invalid = self._tag_counts(result)
        self._preview_panel.set_image(
            path,
            f"{self._active_index + 1} / {len(self._image_paths)}",
            valid,
            invalid,
        )

    def _refresh_tags(self) -> None:
        self._clear_layout(self._tag_layout)
        if not self._image_paths:
            return

        path = self._image_paths[self._active_index]
        result = self._result_for_path(path)
        if result is None:
            label = QLabel(self._t.t("llm_tagger_waiting"), self._tag_container)
            label.setStyleSheet(f"color: {_llm_colors()['fg3']}; font-size: {_fs('fs_10')};")
            self._tag_layout.addWidget(label)
            return
        if path in self._error_by_path:
            label = QLabel(result.raw_text, self._tag_container)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {_llm_colors()['hot']}; font-size: {_fs('fs_10')};")
            self._tag_layout.addWidget(label)
            return
        if not result.parsed_tags:
            label = QLabel(self._t.t("llm_tagger_empty_result"), self._tag_container)
            label.setStyleSheet(f"color: {_llm_colors()['fg3']}; font-size: {_fs('fs_10')};")
            self._tag_layout.addWidget(label)
            return

        density = _llm_density(self._layout_density)
        tag_height = density["tag_h"] + (self._tag_density - 2) * 2
        tag_padding = density["tag_px"] + max(0, self._tag_density - 2)
        for index, parsed_tag in enumerate(result.parsed_tags):
            chip = _LLMTagChip(
                index,
                parsed_tag,
                self._t,
                effective_valid=self._effective_tag_valid(result, index),
                tag_height=tag_height,
                tag_padding=tag_padding,
                parent=self._tag_container,
            )
            chip.toggled_manual.connect(self._toggle_current_tag)
            self._tag_layout.addWidget(chip)

    def _refresh_thumbs(self) -> None:
        self._clear_layout(self._thumb_layout)
        thumb_h = self._thumb_size
        thumb_w = max(24, int(self._thumb_size * 0.78)) if self._portrait_layout else self._thumb_size
        for index, path in enumerate(self._image_paths):
            thumb = _LLMThumbButton(index, path, thumb_width=thumb_w, thumb_height=thumb_h, parent=self._thumb_container)
            thumb.set_selected(index == self._active_index)
            thumb.selected.connect(self._set_active_index)
            thumb.remove_requested.connect(self._remove_image)
            self._thumb_layout.addWidget(thumb)

        add_btn = QPushButton("+", self._thumb_container)
        add_btn.setFixedSize(_dp(thumb_w), _dp(thumb_h))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip(self._t.t("llm_tagger_add_images"))
        add_btn.clicked.connect(self._add_images_dialog)
        c = _llm_colors()
        add_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {c['fg3']}; border: 1px dashed {c['dash']}; "
            f"border-radius: 2px; font-size: {_fs('fs_12')}; padding: 0px; }}"
            f"QPushButton:hover {{ color: {c['fg1']}; border-color: {c['fg2']}; }}"
        )
        self._thumb_layout.addWidget(add_btn)
        self._thumb_layout.addStretch()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _result_for_path(self, path: str):
        for result in self._results:
            if result.image_path == path:
                return result
        return None

    def _effective_tag_valid(self, result, index: int) -> bool:
        path = result.image_path
        if index in self._manual_invalid.get(path, set()):
            return False
        if index in self._manual_valid.get(path, set()):
            return True
        if not (0 <= index < len(result.parsed_tags)):
            return False
        return bool(result.parsed_tags[index].is_valid)

    def _toggle_current_tag(self, index: int) -> None:
        if not self._image_paths:
            return
        result = self._result_for_path(self._image_paths[self._active_index])
        if result is None or not (0 <= index < len(result.parsed_tags)):
            return
        invalid = self._manual_invalid.setdefault(result.image_path, set())
        valid = self._manual_valid.setdefault(result.image_path, set())
        if self._effective_tag_valid(result, index):
            invalid.add(index)
            valid.discard(index)
        else:
            valid.add(index)
            invalid.discard(index)
        self._refresh_status()
        self._refresh_preview()
        self._refresh_tags()

    def _tag_counts(self, result) -> tuple[int, int]:
        if result is None:
            return (0, 0)
        valid = sum(1 for index, _tag in enumerate(result.parsed_tags) if self._effective_tag_valid(result, index))
        return (valid, max(0, len(result.parsed_tags) - valid))

    def _total_valid_count(self) -> int:
        return sum(self._tag_counts(result)[0] for result in self._results)

    # ── Copy / Send ──

    def _collect_result_tags(self, result) -> list[str]:
        if result is None:
            return []
        return [
            tag.name
            for index, tag in enumerate(result.parsed_tags)
            if self._effective_tag_valid(result, index)
        ]

    def _collect_current_tags(self) -> str:
        if not self._image_paths:
            return ""
        result = self._result_for_path(self._image_paths[self._active_index])
        return ", ".join(self._collect_result_tags(result))

    def _collect_all_tags(self) -> str:
        seen: set[str] = set()
        tags: list[str] = []
        for r in self._results:
            for tag in self._collect_result_tags(r):
                if tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
        return ", ".join(tags)

    def _copy_current(self):
        text = self._collect_current_tags()
        if text:
            QApplication.clipboard().setText(text)

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
        c = _llm_colors()
        control = (
            f"font-size: {_fs('fs_10')}; background: {c['bg0']}; color: {c['fg0']}; "
            f"border: 1px solid {c['line']}; border-radius: {_dp(3)}px; padding: {_dp(5)}px {_dp(8)}px;"
        )
        self.setStyleSheet(
            f"QWidget#LLMTopBar, QWidget#LLMFooter {{ background: {c['bg2']}; border-top: 1px solid {c['line']}; border-bottom: 1px solid {c['line']}; }}"
            f"QWidget#LLMEditorPanel {{ background: {c['bg2']}; border-top: 1px solid {c['line']}; }}"
            f"QWidget#LLMStatusStrip {{ background: {c['bg2']}; border-top: 1px solid {c['line']}; border-bottom: 1px solid {c['line']}; }}"
            f"QSplitter#LLMWorkbenchSplitter::handle:vertical {{ background: {c['line']}; height: {_dp(5)}px; margin: 0px; }}"
            f"QSplitter#LLMWorkbenchSplitter::handle:horizontal {{ background: {c['line']}; width: {_dp(5)}px; margin: 0px; }}"
            f"QSplitter#LLMWorkbenchSplitter::handle:vertical:hover {{ background: {c['accent_text']}; }}"
            f"QSplitter#LLMWorkbenchSplitter::handle:horizontal:hover {{ background: {c['accent_text']}; }}"
            f"QComboBox, QLineEdit, QTextEdit {{ {control} }}"
            f"QComboBox::drop-down {{ border: none; width: {_dp(18)}px; }}"
            f"QPushButton {{ font-size: {_fs('fs_10')}; background: transparent; color: {c['fg1']}; "
            f"border: 1px solid {c['line2']}; border-radius: 0px; padding: {_dp(6)}px {_dp(12)}px; letter-spacing: 0.04em; }}"
            f"QPushButton:hover {{ background: {c['bg3']}; color: {c['fg0']}; border-color: {c['line2']}; }}"
            f"QPushButton#LLMPrimaryButton {{ background: {c['accent']}; color: {c['accent_text']}; border-color: {c['accent_hover']}; }}"
            f"QPushButton#LLMPrimaryButton:hover {{ background: {c['accent_hover']}; color: {c['accent_text']}; border-color: {c['accent_hover']}; }}"
            f"QPushButton#LLMDangerButton {{ color: {c['hot']}; border-color: {c['hot']}; }}"
            f"QPushButton#LLMIconButton {{ padding: 0px; }}"
            f"QPushButton#LLMToggleButton {{ padding: {_dp(4)}px {_dp(8)}px; }}"
            f"QPushButton#LLMToggleButton:checked {{ color: {c['fg0']}; background: {c['bg3']}; border-color: {c['fg2']}; }}"
            f"QPushButton#SecondaryButton {{ color: {c['fg1']}; background: transparent; border-color: {c['line2']}; }}"
            f"QScrollArea {{ background: {c['bg1']}; border: none; }}"
            f"QScrollArea#LLMThumbStrip {{ background: {c['bg1']}; border-top: 1px solid {c['line']}; }}"
            f"QProgressBar {{ background: {c['bg3']}; border: none; border-radius: 1px; }}"
            f"QProgressBar::chunk {{ background: {c['accent_text']}; border-radius: 1px; }}"
        )
        self._mode_switch.apply_theme()
        self._stats_label.setStyleSheet(f"color: {c['fg2']}; font-size: {_fs('fs_10')};")
        self._valid_total_label.setStyleSheet(f"color: {c['fg1']}; font-size: {_fs('fs_10')};")
        self._error_label.setStyleSheet(f"color: {c['hot']}; font-size: {_fs('fs_10')};")
        self._tag_container.setStyleSheet(f"background: {c['bg1']};")
        self._thumb_container.setStyleSheet(f"background: {c['bg1']};")
        self._drop_zone.apply_theme()
        self._drop_zone.setStyleSheet(
            f"background: {c['bg0']}; border: 1.5px dashed {c['dash']}; border-radius: 4px;"
        )
        self._drop_zone._label.setStyleSheet(
            f"color: {c['fg2']}; font-size: {_fs('fs_11')}; border: none;"
        )
        self._preview_panel.apply_theme()
        self._refresh_toolbar()
        self._refresh_status()
        self._refresh_tags()
        self._refresh_thumbs()

    def retranslate_ui(self):
        self._name_edit.setPlaceholderText(self._t.t("llm_tagger_preset_name"))
        self._prompt_edit.setPlaceholderText(self._t.t("interrogator_llm_prompt"))
        self._api_toggle.setText(self._t.t("llm_tagger_use_separate_api"))
        self._separate_url.setPlaceholderText(self._t.t("llm_tagger_api_base_url"))
        self._separate_key.setPlaceholderText(self._t.t("llm_tagger_api_key"))
        self._separate_model.setPlaceholderText(self._t.t("llm_tagger_api_model"))
        self._edit_btn.setToolTip(self._t.t("llm_tagger_edit_section"))
        self._layout_btn.setToolTip(self._t.t("llm_tagger_reset_layout"))
        self._copy_current_btn.setText(self._t.t("llm_tagger_copy_current"))
        self._copy_all_btn.setText(self._t.t("llm_tagger_copy_all"))
        self._send_all_btn.setText(self._t.t("llm_tagger_send_all"))
        self._mode_switch.retranslate_ui()
        self._refresh_all()


# ═══════════════════════════════════════════════════
#  Drop Zone (shared)
# ═══════════════════════════════════════════════════

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
                self, self._t.t("interrogator_select_image"), "", image_filter(self._t, include_gif=True)
            )
            if paths:
                self._set_images(paths)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, self._t.t("interrogator_select_image"), "", image_filter(self._t, include_gif=True)
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
        max_h = max(_dp(40), self.height() - _dp(30))
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
    """Image interrogator with integrated Local / LLM modes."""

    send_to_input = pyqtSignal(str)
    model_dir_changed = pyqtSignal(str)
    python_path_changed = pyqtSignal(str)
    settings_changed = pyqtSignal()

    def __init__(self, translator: Translator, parent=None,
                 model_dir: str = "", python_path: str = ""):
        super().__init__(parent)
        self._t = translator

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._mode_stack = QStackedWidget(self)

        self._local_tab = _LocalTaggerTab(translator, self,
                                          model_dir=model_dir,
                                          python_path=python_path)
        self._local_tab.send_to_input.connect(self.send_to_input.emit)
        self._local_tab.model_dir_changed.connect(self.model_dir_changed.emit)
        self._local_tab.python_path_changed.connect(self.python_path_changed.emit)
        self._local_tab.mode_changed.connect(self._set_mode)
        self._local_tab.settings_changed.connect(self.settings_changed.emit)
        self._mode_stack.addWidget(self._local_tab)

        self._llm_tab = _LLMTaggerTab(translator, self)
        self._llm_tab.send_to_input.connect(self.send_to_input.emit)
        self._llm_tab.mode_changed.connect(self._set_mode)
        self._llm_tab.settings_changed.connect(self.settings_changed.emit)
        self._mode_stack.addWidget(self._llm_tab)

        root.addWidget(self._mode_stack, 1)
        self._set_mode(1)
        self.apply_theme()

    def set_api_settings(self, base_url: str, api_key: str, model: str):
        self._llm_tab.set_api_settings(base_url, api_key, model)

    def set_tag_dictionary(self, dictionary):
        self._local_tab.set_tag_dictionary(dictionary)
        self._llm_tab.set_tag_dictionary(dictionary)

    def apply_interrogator_settings(self, settings):
        self._local_tab.apply_local_settings(settings)
        self._llm_tab.apply_llm_settings(settings)

    def collect_interrogator_settings(self) -> dict:
        data = self._llm_tab.collect_llm_settings()
        data.update(self._local_tab.collect_local_settings())
        return data

    def apply_llm_settings(self, settings):
        """Backward-compatible alias for older callers."""
        self._llm_tab.apply_llm_settings(settings)

    def collect_llm_settings(self) -> dict:
        """Backward-compatible alias for older callers."""
        return self._llm_tab.collect_llm_settings()

    def load_image(self, path: str, *, prefer_llm: bool = False) -> None:
        if not path:
            return
        if prefer_llm:
            self.load_images([path])
            return
        self._set_mode(0)
        self._local_tab.load_image(path)

    def load_images(self, paths: list[str]) -> None:
        valid = [path for path in paths if path]
        if not valid:
            return
        self._set_mode(1 if len(valid) > 1 else self._mode_stack.currentIndex())
        if self._mode_stack.currentIndex() == 0 and len(valid) == 1:
            self._local_tab.load_image(valid[0])
        else:
            self._llm_tab.load_images(valid)

    def _set_mode(self, index: int) -> None:
        index = 1 if index == 1 else 0
        self._mode_stack.setCurrentIndex(index)
        self._local_tab.set_mode(index)
        self._llm_tab.set_mode(index)

    def apply_theme(self):
        self._local_tab.apply_theme()
        self._local_tab.set_mode(self._mode_stack.currentIndex())
        self._llm_tab.apply_theme()

    def retranslate_ui(self):
        self._local_tab.retranslate_ui()
        self._llm_tab.retranslate_ui()
