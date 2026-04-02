from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class DockPosition(str, Enum):
    LEFT = 'left'
    RIGHT = 'right'
    TOP = 'top'
    BOTTOM = 'bottom'
    FLOATING = 'floating'


def clamp_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        return min(maximum, max(minimum, float(value)))
    except (TypeError, ValueError):
        return fallback


def clamp_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError):
        return fallback


DEFAULT_WINDOW_WIDTH = 1440
DEFAULT_WINDOW_HEIGHT = 860
DEFAULT_SUMMARY_PROMPT = (
    "Please summarize the following tag generation history into a concise set "
    "of stable user preferences and useful tag patterns.\n\n{{content}}"
)
CONFIG_BUNDLE_VERSION = 1
CONFIG_SCOPE_SETTINGS_PAGE = "settings_page"
CONFIG_SCOPE_FULL_PROFILE = "full_profile"
DEFAULT_DOCK_COLLAPSED_THICKNESS = 40
DEFAULT_DOCK_EXPANDED_VERTICAL_SIZE = 132
DEFAULT_DOCK_EXPANDED_HORIZONTAL_SIZE = 84


@dataclass
class PromptEntry:
    name: str = "Main Prompt"
    role: str = "system"
    depth: int = 0
    order: int = 1
    enabled: bool = True
    content: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptEntry":
        return cls(
            name=str(data.get("name", cls.name)),
            role=str(data.get("role", cls.role)),
            depth=int(data.get("depth", cls.depth) or 0),
            order=int(data.get("order", cls.order) or 0),
            enabled=bool(data.get("enabled", True)),
            content=str(data.get("content", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExampleEntry:
    image_path: str = ""
    tags: str = ""
    description: str = ""
    order: int = 100
    depth: int = 4

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExampleEntry":
        return cls(
            image_path=str(data.get("image_path", "")),
            tags=str(data.get("tags", "")),
            description=str(data.get("description", data.get("desc", ""))),
            order=int(data.get("order", cls.order) or cls.order),
            depth=int(data.get("depth", cls.depth) or cls.depth),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArtistEntry:
    name: str = ""
    artist_string: str = ""
    reference_images: list[str] = field(default_factory=list)
    order: int = 100
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtistEntry":
        return cls(
            name=str(data.get("name", "")),
            artist_string=str(data.get("artist_string", "")),
            reference_images=list(data.get("reference_images", [])),
            order=int(data.get("order", cls.order) or cls.order),
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutfitEntry:
    name: str = ""
    tags: str = ""
    active: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutfitEntry":
        return cls(
            name=str(data.get("name", "")),
            tags=str(data.get("tags", "")),
            active=bool(data.get("active", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OCEntry:
    character_name: str = ""
    tags: str = ""
    reference_images: list[str] = field(default_factory=list)
    outfits: list[OutfitEntry] = field(default_factory=list)
    order: int = 77
    depth: int = 4
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OCEntry":
        outfits = [OutfitEntry.from_dict(o) for o in data.get("outfits", [])]
        return cls(
            character_name=str(data.get("character_name", "")),
            tags=str(data.get("tags", "")),
            reference_images=list(data.get("reference_images", [])),
            outfits=outfits,
            order=int(data.get("order", cls.order) or cls.order),
            depth=int(data.get("depth", cls.depth) or cls.depth),
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['outfits'] = [o.to_dict() for o in self.outfits]
        return d

    def merged_tags(self) -> str:
        """Return character tags + all active outfit tags merged."""
        parts = [self.tags] if self.tags.strip() else []
        for o in self.outfits:
            if o.active and o.tags.strip():
                parts.append(o.tags)
        return ", ".join(parts)


@dataclass
class HistoryEntry:
    input_text: str = ""
    output_text: str = ""
    timestamp: str = ""
    model: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryEntry":
        return cls(
            input_text=str(data.get("input_text", "")),
            output_text=str(data.get("output_text", "")),
            timestamp=str(data.get("timestamp", "")),
            model=str(data.get("model", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WidgetState:
    widget_id: str
    visible: bool = True
    docked: bool = False
    x: int = 0
    y: int = 0
    width: int = 320
    height: int = 220
    dock_slot: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WidgetState":
        return cls(
            widget_id=str(data.get("widget_id", "")),
            visible=bool(data.get("visible", True)),
            docked=bool(data.get("docked", False)),
            x=int(data.get("x", 0) or 0),
            y=int(data.get("y", 0) or 0),
            width=int(data.get("width", 320) or 320),
            height=int(data.get("height", 220) or 220),
            dock_slot=str(data.get("dock_slot", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DockState:
    position: str = DockPosition.LEFT
    expanded: bool = False
    collapsed_thickness: int = DEFAULT_DOCK_COLLAPSED_THICKNESS
    expanded_vertical_size: int = DEFAULT_DOCK_EXPANDED_VERTICAL_SIZE
    expanded_horizontal_size: int = DEFAULT_DOCK_EXPANDED_HORIZONTAL_SIZE
    floating_x: int = 120
    floating_y: int = 120
    floating_width: int = 160
    floating_height: int = 220
    last_docked_position: str = DockPosition.LEFT

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DockState":
        try:
            legacy_size = int(data.get("size", 0) or 0)
        except (TypeError, ValueError):
            legacy_size = 0
        legacy_expanded_size = legacy_size if legacy_size > DEFAULT_DOCK_COLLAPSED_THICKNESS else 0

        return cls(
            position=str(data.get("position", DockPosition.LEFT)),
            expanded=bool(data.get("expanded", False)),
            collapsed_thickness=clamp_int(
                data.get("collapsed_thickness", DEFAULT_DOCK_COLLAPSED_THICKNESS),
                DEFAULT_DOCK_COLLAPSED_THICKNESS,
                24, 99999,
            ),
            expanded_vertical_size=clamp_int(
                data.get("expanded_vertical_size", legacy_expanded_size or DEFAULT_DOCK_EXPANDED_VERTICAL_SIZE),
                DEFAULT_DOCK_EXPANDED_VERTICAL_SIZE,
                72, 99999,
            ),
            expanded_horizontal_size=clamp_int(
                data.get("expanded_horizontal_size", legacy_expanded_size or DEFAULT_DOCK_EXPANDED_HORIZONTAL_SIZE),
                DEFAULT_DOCK_EXPANDED_HORIZONTAL_SIZE,
                60, 99999,
            ),
            floating_x=int(data.get("floating_x", 120) or 120),
            floating_y=int(data.get("floating_y", 120) or 120),
            floating_width=int(data.get("floating_width", 160) or 160),
            floating_height=int(data.get("floating_height", 220) or 220),
            last_docked_position=str(data.get("last_docked_position", DockPosition.LEFT)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WindowState:
    x: int = 0
    y: int = 0
    width: int = DEFAULT_WINDOW_WIDTH
    height: int = DEFAULT_WINDOW_HEIGHT
    maximized: bool = False
    pinned: bool = False
    available_screen_x: int = 0
    available_screen_y: int = 0
    available_screen_width: int = DEFAULT_WINDOW_WIDTH
    available_screen_height: int = DEFAULT_WINDOW_HEIGHT
    screen_device_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WindowState":
        return cls(
            x=int(data.get("x", 0) or 0),
            y=int(data.get("y", 0) or 0),
            width=int(data.get("width", DEFAULT_WINDOW_WIDTH) or DEFAULT_WINDOW_WIDTH),
            height=int(data.get("height", DEFAULT_WINDOW_HEIGHT) or DEFAULT_WINDOW_HEIGHT),
            maximized=bool(data.get("maximized", False)),
            pinned=bool(data.get("pinned", False)),
            available_screen_x=int(data.get("available_screen_x", 0) or 0),
            available_screen_y=int(data.get("available_screen_y", 0) or 0),
            available_screen_width=int(data.get("available_screen_width", DEFAULT_WINDOW_WIDTH) or DEFAULT_WINDOW_WIDTH),
            available_screen_height=int(data.get("available_screen_height", DEFAULT_WINDOW_HEIGHT) or DEFAULT_WINDOW_HEIGHT),
            screen_device_name=str(data.get("screen_device_name", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AppSettings:
    api_base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 1.0
    top_p: float = 1.0
    top_k: int | None = None
    freq_penalty: float = 0.0
    pres_penalty: float = 0.0
    max_tokens: int = 64000
    stream: bool = True
    memory_mode: bool = True
    summary_prompt: str = DEFAULT_SUMMARY_PROMPT
    language: str = "zh-CN"
    ui_scale_percent: int = 100
    body_font_point_size: int = 11
    font_profile: str = "wenkai"
    custom_font_id: str = ""
    theme: str = "dark"
    card_opacity: int = 82
    custom_bg_image: str = ""
    bg_blur: int = 30
    bg_opacity: int = 40
    bg_brightness: int = 0
    workspace_menu_order: list[str] | None = None
    image_manager_folder: str = ""
    # TAG extraction markers
    tag_full_start: str = "[TAGS]"
    tag_full_end: str = "[/TAGS]"
    tag_nochar_start: str = "[NOTAGS]"
    tag_nochar_end: str = "[/NOTAGS]"
    # Defaults for new entries
    default_example_order: int = 100
    default_example_depth: int = 4
    default_oc_order: int = 77
    default_oc_depth: int = 4

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        top_k_raw = data.get("top_k")
        if top_k_raw in ("", None):
            top_k = None
        else:
            try:
                top_k = max(0, int(top_k_raw))
            except (TypeError, ValueError):
                top_k = None

        return cls(
            api_base_url=str(data.get("api_base_url", data.get("apiUrl", ""))),
            api_key=str(data.get("api_key", data.get("apiKey", ""))),
            model=str(data.get("model", "")),
            temperature=clamp_float(data.get("temperature", 1.0), 1.0, 0.0, 2.0),
            top_p=clamp_float(data.get("top_p", data.get("topP", 1.0)), 1.0, 0.0, 1.0),
            top_k=top_k,
            freq_penalty=clamp_float(data.get("freq_penalty", data.get("freqPenalty", 0.0)), 0.0, -2.0, 2.0),
            pres_penalty=clamp_float(data.get("pres_penalty", data.get("presPenalty", 0.0)), 0.0, -2.0, 2.0),
            max_tokens=clamp_int(data.get("max_tokens", data.get("maxTokens", 2048)), 2048, 1, 200000),
            stream=bool(data.get("stream", True)),
            memory_mode=bool(data.get("memory_mode", True)),
            summary_prompt=str(data.get("summary_prompt", DEFAULT_SUMMARY_PROMPT)),
            language=str(data.get("language", "zh-CN") or "zh-CN"),
            ui_scale_percent=clamp_int(data.get("ui_scale_percent", 100), 100, 50, 300),
            body_font_point_size=clamp_int(data.get("body_font_point_size", 11), 11, 8, 24),
            font_profile=str(data.get("font_profile", "wenkai") or "wenkai"),
            custom_font_id=str(data.get("custom_font_id", "") or ""),
            theme=str(data.get("theme", "dark") or "dark"),
            card_opacity=clamp_int(data.get("card_opacity", 82), 82, 30, 100),
            custom_bg_image=str(data.get("custom_bg_image", "") or ""),
            bg_blur=clamp_int(data.get("bg_blur", 30), 30, 0, 100),
            bg_opacity=clamp_int(data.get("bg_opacity", 40), 40, 0, 100),
            bg_brightness=clamp_int(data.get("bg_brightness", 0), 0, 0, 100),
            workspace_menu_order=data.get("workspace_menu_order"),
            image_manager_folder=str(data.get("image_manager_folder", "") or ""),
            tag_full_start=str(data.get("tag_full_start", "[TAGS]") or "[TAGS]"),
            tag_full_end=str(data.get("tag_full_end", "[/TAGS]") or "[/TAGS]"),
            tag_nochar_start=str(data.get("tag_nochar_start", "[NOTAGS]") or "[NOTAGS]"),
            tag_nochar_end=str(data.get("tag_nochar_end", "[/NOTAGS]") or "[/NOTAGS]"),
            default_example_order=clamp_int(data.get("default_example_order", 100), 100, 0, 9999),
            default_example_depth=clamp_int(data.get("default_example_depth", 4), 4, 0, 999),
            default_oc_order=clamp_int(data.get("default_oc_order", 77), 77, 0, 9999),
            default_oc_depth=clamp_int(data.get("default_oc_depth", 4), 4, 0, 999),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ErrorReport:
    kind: str = "runtime_error"
    summary: str = ""
    details: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    report_path: str = ""


@dataclass
class ConfigBundle:
    version: int = CONFIG_BUNDLE_VERSION
    scope: str = CONFIG_SCOPE_SETTINGS_PAGE
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigBundle":
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        try:
            version = int(data.get("version", CONFIG_BUNDLE_VERSION) or CONFIG_BUNDLE_VERSION)
        except (TypeError, ValueError):
            version = CONFIG_BUNDLE_VERSION
        scope = str(data.get("scope", CONFIG_SCOPE_SETTINGS_PAGE) or CONFIG_SCOPE_SETTINGS_PAGE)
        return cls(version=version, scope=scope, payload=payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "scope": self.scope,
            "payload": self.payload,
        }


@dataclass
class AppState:
    settings: AppSettings = field(default_factory=AppSettings)
    window: WindowState = field(default_factory=WindowState)
    dock: DockState = field(default_factory=DockState)
    widgets: list[WidgetState] = field(default_factory=list)
    prompts: list[PromptEntry] = field(default_factory=list)
    examples: list[ExampleEntry] = field(default_factory=list)
    input_history: str = ""

    @classmethod
    def default(cls) -> "AppState":
        return cls(
            prompts=cls._load_default_prompts(),
            examples=cls._load_default_examples(),
            widgets=[
                WidgetState(widget_id="widget-prompts", visible=False, docked=True),
                WidgetState(widget_id="widget-main", visible=True, docked=False, width=640, height=500),
                WidgetState(widget_id="widget-example-1", visible=False, docked=True),
            ],
        )

    @staticmethod
    def _load_default_examples() -> list[ExampleEntry]:
        import json, shutil, uuid
        from pathlib import Path
        res_dir = Path(__file__).parent / "resources"
        json_path = res_dir / "default_examples.json"
        image_src = res_dir / "default_example.png"
        if not json_path.exists():
            return [ExampleEntry()]
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            examples = []
            for i, d in enumerate(data):
                if not isinstance(d, dict):
                    continue
                entry = ExampleEntry.from_dict(d)
                # Copy bundled image to AppData examples dir
                if not entry.image_path and image_src.exists() and i == 0:
                    import os
                    appdata = os.environ.get("APPDATA", "")
                    if appdata:
                        examples_dir = Path(appdata) / "HainTag" / "examples"
                        examples_dir.mkdir(parents=True, exist_ok=True)
                        dest = examples_dir / f"{uuid.uuid4().hex}.png"
                        shutil.copy2(image_src, dest)
                        entry.image_path = str(dest)
                examples.append(entry)
            return examples or [ExampleEntry()]
        except Exception:
            return [ExampleEntry()]

    @staticmethod
    def _load_default_prompts() -> list[PromptEntry]:
        import json
        from pathlib import Path
        default_path = Path(__file__).parent / "resources" / "default_prompts.json"
        if not default_path.exists():
            return [PromptEntry()]
        try:
            data = json.loads(default_path.read_text(encoding="utf-8"))
            return [PromptEntry.from_dict(d) for d in data if isinstance(d, dict)] or [PromptEntry()]
        except Exception:
            return [PromptEntry()]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppState":
        state = cls.default()
        state.settings = AppSettings.from_dict(data.get("settings", data))
        state.window = WindowState.from_dict(data.get("window", {}))
        state.dock = DockState.from_dict(data.get("dock", {}))
        prompts = data.get("prompts", [])
        examples = data.get("examples", [])
        widgets = data.get("widgets", [])
        state.prompts = [PromptEntry.from_dict(item) for item in prompts] if prompts else state.prompts
        state.examples = [ExampleEntry.from_dict(item) for item in examples] if examples else state.examples
        state.widgets = [WidgetState.from_dict(item) for item in widgets] or state.widgets
        state.input_history = str(data.get("input_history", ""))
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "settings": self.settings.to_dict(),
            "window": self.window.to_dict(),
            "dock": self.dock.to_dict(),
            "widgets": [item.to_dict() for item in self.widgets],
            "prompts": [item.to_dict() for item in self.prompts],
            "examples": [item.to_dict() for item in self.examples],
            "input_history": self.input_history,
        }
