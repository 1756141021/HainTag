from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import (
    AppSettings,
    AppState,
    ConfigBundle,
    DockState,
    ExampleEntry,
    PromptEntry,
    WidgetState,
    WindowState,
    CONFIG_SCOPE_FULL_PROFILE,
)
from ._examples import ExampleStorage
from ._fonts import FontStorage
from ._paths import StoragePaths


class ConfigBundleStorage:
    def __init__(self, paths: StoragePaths, fonts: FontStorage, examples: ExampleStorage) -> None:
        self._paths = paths
        self._fonts = fonts
        self._examples = examples

    def export_config_bundle(
        self,
        target_path: str,
        scope: str,
        *,
        settings: AppSettings,
        prompts: list[PromptEntry] | None = None,
        examples: list[ExampleEntry] | None = None,
        dock: DockState | None = None,
        widgets: list[WidgetState] | None = None,
        window: WindowState | None = None,
    ) -> None:
        payload: dict[str, Any] = {"settings": self._exportable_settings(settings)}
        if scope == CONFIG_SCOPE_FULL_PROFILE:
            payload["prompts"] = [item.to_dict() for item in (prompts or [])]
            payload["examples"] = [self._examples.serialize_example_entry(item) for item in (examples or [])]
            payload["dock"] = (dock or DockState()).to_dict()
            payload["widgets"] = [item.to_dict() for item in (widgets or [])]
            payload["window"] = (window or WindowState()).to_dict()
        font_assets = self._fonts.serialize_font_assets(settings)
        if font_assets:
            payload["font_assets"] = font_assets
        bundle = ConfigBundle(scope=scope, payload=payload)
        Path(target_path).write_text(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def import_config_bundle(self, source_path: str) -> ConfigBundle:
        try:
            data = json.loads(Path(source_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid config bundle") from exc
        if not isinstance(data, dict):
            raise ValueError("Invalid config bundle")
        bundle = ConfigBundle.from_dict(data)
        if not isinstance(bundle.payload, dict) or not bundle.payload:
            raise ValueError("Invalid config bundle")
        return bundle

    def merged_settings_from_bundle(self, bundle: ConfigBundle, current: AppSettings) -> AppSettings:
        settings_data = bundle.payload.get("settings")
        if not isinstance(settings_data, dict):
            raise ValueError("Missing settings payload")
        merged = current.to_dict()
        for key, value in settings_data.items():
            if key in {"api_base_url", "api_key"}:
                continue
            merged[key] = value
        merged["api_base_url"] = current.api_base_url
        merged["api_key"] = current.api_key
        result = AppSettings.from_dict(merged)
        if result.font_profile == "custom" and result.custom_font_id:
            if not self._fonts._font_exists(result.custom_font_id):
                result.font_profile = "default"
                result.custom_font_id = ""
        return result

    def state_from_bundle(self, bundle: ConfigBundle, current_state: AppState) -> AppState:
        next_state = AppState.default()
        payload = bundle.payload
        font_assets = payload.get("font_assets", [])
        if isinstance(font_assets, list) and font_assets:
            self._fonts.deserialize_font_assets(font_assets)
        next_state.settings = self.merged_settings_from_bundle(bundle, current_state.settings)

        prompts_data = payload.get("prompts", [item.to_dict() for item in current_state.prompts])
        if isinstance(prompts_data, list):
            next_state.prompts = [PromptEntry.from_dict(item) for item in prompts_data if isinstance(item, dict)] or [PromptEntry()]
        else:
            next_state.prompts = [PromptEntry()]

        examples_data = payload.get("examples", [self._examples.serialize_example_entry(item) for item in current_state.examples])
        if isinstance(examples_data, list):
            next_state.examples = [self._examples.deserialize_example_entry(item) for item in examples_data if isinstance(item, dict)]
        else:
            next_state.examples = []

        dock_data = payload.get("dock", current_state.dock.to_dict())
        next_state.dock = DockState.from_dict(dock_data if isinstance(dock_data, dict) else {})

        widgets_data = payload.get("widgets", [item.to_dict() for item in current_state.widgets])
        if isinstance(widgets_data, list):
            next_state.widgets = [WidgetState.from_dict(item) for item in widgets_data if isinstance(item, dict)] or current_state.widgets
        else:
            next_state.widgets = current_state.widgets

        window_data = payload.get("window", current_state.window.to_dict())
        next_state.window = WindowState.from_dict(window_data if isinstance(window_data, dict) else {})
        next_state.input_history = current_state.input_history
        return next_state

    def _exportable_settings(self, settings: AppSettings) -> dict[str, Any]:
        payload = settings.to_dict()
        payload.pop("api_base_url", None)
        payload.pop("api_key", None)
        return payload
