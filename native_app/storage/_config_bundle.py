from __future__ import annotations

import base64
import copy
import json
import uuid
from pathlib import Path
from typing import Any

from ..models import (
    AppSettings,
    AppState,
    ArtistEntry,
    ConfigBundle,
    DockState,
    ExampleEntry,
    HistoryEntry,
    OCEntry,
    PromptEntry,
    WidgetState,
    WindowState,
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
from ._examples import ExampleStorage
from ._fonts import FontStorage
from ._paths import StoragePaths

_SETTINGS_PAGE_SCOPES = {
    CONFIG_SCOPE_APPEARANCE,
    CONFIG_SCOPE_MODEL_PARAMS,
    CONFIG_SCOPE_ENTRY_DEFAULTS,
    CONFIG_SCOPE_TAG_MARKERS,
    CONFIG_SCOPE_WINDOW_LAYOUT,
}
_SETTING_FIELDS_BY_SCOPE = {
    CONFIG_SCOPE_APPEARANCE: {
        "language",
        "ui_scale_percent",
        "body_font_point_size",
        "font_profile",
        "custom_font_id",
        "theme",
        "card_opacity",
        "custom_bg_image",
        "bg_blur",
        "bg_opacity",
        "bg_brightness",
    },
    CONFIG_SCOPE_MODEL_PARAMS: {
        "model",
        "temperature",
        "top_p",
        "top_k",
        "freq_penalty",
        "pres_penalty",
        "max_tokens",
        "stream",
        "memory_mode",
        "summary_prompt",
        "tagger_model_dir",
        "tagger_python_path",
        "tagger_local_enabled_categories",
        "tagger_local_general_threshold",
        "tagger_local_character_threshold",
        "tagger_local_show_confidence",
        "tagger_local_preview_ratio",
        "tagger_local_layout_v2",
        "tagger_llm_use_separate",
        "tagger_llm_model",
        "tagger_llm_presets",
        "tagger_llm_active_preset",
        "tagger_llm_layout_density",
        "tagger_llm_preview_ratio",
        "tagger_llm_thumb_size",
        "tagger_llm_tag_density",
    },
    CONFIG_SCOPE_ENTRY_DEFAULTS: {
        "default_example_order",
        "default_example_depth",
        "default_oc_order",
        "default_oc_depth",
    },
    CONFIG_SCOPE_TAG_MARKERS: {
        "tag_full_start",
        "tag_full_end",
        "tag_nochar_start",
        "tag_nochar_end",
    },
    CONFIG_SCOPE_WINDOW_LAYOUT: {
        "workspace_menu_order",
        "image_manager_folder",
        "send_mode",
        "history_retention_days",
        "library_last_section",
        "destroy_templates",
        "active_destroy_template",
    },
}
_BLOCKED_SETTING_FIELDS = {"api_base_url", "api_key", "tagger_llm_api_key", "tagger_llm_base_url"}


class ConfigBundleStorage:
    def __init__(self, paths: StoragePaths, fonts: FontStorage, examples: ExampleStorage) -> None:
        self._paths = paths
        self._fonts = fonts
        self._examples = examples

    def export_config_bundle(
        self,
        target_path: str,
        scopes: str | list[str],
        *,
        settings: AppSettings,
        prompts: list[PromptEntry] | None = None,
        examples: list[ExampleEntry] | None = None,
        dock: DockState | None = None,
        widgets: list[WidgetState] | None = None,
        window: WindowState | None = None,
        artists: list[ArtistEntry] | None = None,
        ocs: list[OCEntry] | None = None,
        history: list[HistoryEntry] | None = None,
    ) -> None:
        normalized_scopes = self._normalize_scopes(scopes)
        payload: dict[str, Any] = {}

        settings_payload = self._exportable_settings(settings, normalized_scopes)
        if settings_payload:
            payload["settings"] = settings_payload

        if CONFIG_SCOPE_PROMPTS in normalized_scopes:
            payload["prompts"] = [item.to_dict() for item in (prompts or [])]
        if CONFIG_SCOPE_EXAMPLES in normalized_scopes:
            payload["examples"] = [self._examples.serialize_example_entry(item) for item in (examples or [])]
        if CONFIG_SCOPE_OC_LIBRARY in normalized_scopes:
            payload["ocs"] = [self._serialize_library_entry(item) for item in (ocs or [])]
        if CONFIG_SCOPE_ARTIST_LIBRARY in normalized_scopes:
            payload["artists"] = [self._serialize_library_entry(item) for item in (artists or [])]
        if CONFIG_SCOPE_WINDOW_LAYOUT in normalized_scopes:
            payload["dock"] = (dock or DockState()).to_dict()
            payload["widgets"] = [item.to_dict() for item in (widgets or [])]
            payload["window"] = (window or WindowState()).to_dict()
        if CONFIG_SCOPE_HISTORY in normalized_scopes:
            payload["history"] = [item.to_dict() for item in (history or [])]

        font_assets = self._fonts.serialize_font_assets(settings)
        if font_assets and "custom_font_id" in settings_payload:
            payload["font_assets"] = font_assets

        bundle = ConfigBundle(scope=normalized_scopes, payload=payload)
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

    def merged_settings_from_bundle(
        self,
        bundle: ConfigBundle,
        current: AppSettings,
        scopes: str | list[str] | None = None,
    ) -> AppSettings:
        requested_scopes = self._requested_scopes(bundle, scopes)
        settings_data = bundle.payload.get("settings")
        if not isinstance(settings_data, dict):
            return current

        merged = current.to_dict()
        allowed_fields = self._settings_fields_for_scopes(requested_scopes)
        for key, value in settings_data.items():
            if key in _BLOCKED_SETTING_FIELDS or key not in allowed_fields:
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

    def state_from_bundle(
        self,
        bundle: ConfigBundle,
        current_state: AppState,
        scopes: str | list[str] | None = None,
    ) -> AppState:
        requested_scopes = self._requested_scopes(bundle, scopes)
        next_state = copy.deepcopy(current_state)
        payload = bundle.payload

        font_assets = payload.get("font_assets", [])
        if isinstance(font_assets, list) and font_assets:
            self._fonts.deserialize_font_assets(font_assets)

        next_state.settings = self.merged_settings_from_bundle(bundle, current_state.settings, requested_scopes)

        if CONFIG_SCOPE_PROMPTS in requested_scopes:
            prompts_data = payload.get("prompts")
            if isinstance(prompts_data, list):
                next_state.prompts = [PromptEntry.from_dict(item) for item in prompts_data if isinstance(item, dict)] or [PromptEntry()]

        if CONFIG_SCOPE_EXAMPLES in requested_scopes:
            examples_data = payload.get("examples")
            if isinstance(examples_data, list):
                next_state.examples = [self._examples.deserialize_example_entry(item) for item in examples_data if isinstance(item, dict)]

        if CONFIG_SCOPE_WINDOW_LAYOUT in requested_scopes:
            dock_data = payload.get("dock")
            if isinstance(dock_data, dict):
                next_state.dock = DockState.from_dict(dock_data)

            widgets_data = payload.get("widgets")
            if isinstance(widgets_data, list):
                next_state.widgets = [WidgetState.from_dict(item) for item in widgets_data if isinstance(item, dict)] or current_state.widgets

            window_data = payload.get("window")
            if isinstance(window_data, dict):
                next_state.window = WindowState.from_dict(window_data)

        return next_state

    def library_from_bundle(
        self,
        bundle: ConfigBundle,
        current_artists: list[ArtistEntry],
        current_ocs: list[OCEntry],
        scopes: str | list[str] | None = None,
    ) -> tuple[list[ArtistEntry], list[OCEntry]]:
        requested_scopes = self._requested_scopes(bundle, scopes)
        artists = current_artists
        ocs = current_ocs
        if CONFIG_SCOPE_ARTIST_LIBRARY in requested_scopes:
            artists_data = bundle.payload.get("artists")
            if isinstance(artists_data, list):
                artists = [
                    ArtistEntry.from_dict(self._deserialize_library_entry(item))
                    for item in artists_data
                    if isinstance(item, dict)
                ]
        if CONFIG_SCOPE_OC_LIBRARY in requested_scopes:
            ocs_data = bundle.payload.get("ocs")
            if isinstance(ocs_data, list):
                ocs = [
                    OCEntry.from_dict(self._deserialize_library_entry(item))
                    for item in ocs_data
                    if isinstance(item, dict)
                ]
        return artists, ocs

    def history_from_bundle(
        self,
        bundle: ConfigBundle,
        current_history: list[HistoryEntry],
        scopes: str | list[str] | None = None,
    ) -> list[HistoryEntry]:
        requested_scopes = self._requested_scopes(bundle, scopes)
        if CONFIG_SCOPE_HISTORY not in requested_scopes:
            return current_history
        history_data = bundle.payload.get("history")
        if not isinstance(history_data, list):
            return current_history
        return [HistoryEntry.from_dict(item) for item in history_data if isinstance(item, dict)]

    def _exportable_settings(self, settings: AppSettings, scopes: list[str]) -> dict[str, Any]:
        source = settings.to_dict()
        payload: dict[str, Any] = {}
        for key in self._settings_fields_for_scopes(scopes):
            if key in _BLOCKED_SETTING_FIELDS:
                continue
            if key in source:
                payload[key] = source[key]
        payload.pop("api_base_url", None)
        payload.pop("api_key", None)
        return payload

    def _settings_fields_for_scopes(self, scopes: list[str]) -> set[str]:
        fields: set[str] = set()
        for scope in scopes:
            fields.update(_SETTING_FIELDS_BY_SCOPE.get(scope, set()))
        return fields

    def _requested_scopes(self, bundle: ConfigBundle, scopes: str | list[str] | None) -> list[str]:
        bundle_scopes = set(self._normalize_scopes(bundle.scope))
        selected_scopes = set(self._normalize_scopes(scopes)) if scopes is not None else bundle_scopes
        return [scope for scope in CONFIG_FINE_SCOPES if scope in bundle_scopes and scope in selected_scopes]

    def _normalize_scopes(self, scopes: str | list[str] | None) -> list[str]:
        if scopes == CONFIG_SCOPE_FULL_PROFILE:
            return list(CONFIG_FINE_SCOPES)
        if scopes == CONFIG_SCOPE_SETTINGS_PAGE or scopes is None:
            return [scope for scope in CONFIG_FINE_SCOPES if scope in _SETTINGS_PAGE_SCOPES]

        raw_scopes = scopes if isinstance(scopes, list) else [scopes]
        seen: set[str] = set()
        normalized: list[str] = []
        for item in raw_scopes:
            scope = str(item)
            if scope == CONFIG_SCOPE_FULL_PROFILE:
                for fine_scope in CONFIG_FINE_SCOPES:
                    if fine_scope not in seen:
                        seen.add(fine_scope)
                        normalized.append(fine_scope)
                continue
            if scope == CONFIG_SCOPE_SETTINGS_PAGE:
                for fine_scope in CONFIG_FINE_SCOPES:
                    if fine_scope in _SETTINGS_PAGE_SCOPES and fine_scope not in seen:
                        seen.add(fine_scope)
                        normalized.append(fine_scope)
                continue
            if scope in CONFIG_FINE_SCOPES and scope not in seen:
                seen.add(scope)
                normalized.append(scope)
        return normalized

    def _serialize_library_entry(self, entry: ArtistEntry | OCEntry) -> dict[str, Any]:
        payload = entry.to_dict()
        assets = []
        for image_path in payload.get("reference_images", []):
            path = Path(str(image_path))
            if not path.exists():
                continue
            try:
                assets.append({
                    "suffix": path.suffix.lower() or ".png",
                    "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                })
            except OSError:
                continue
        payload["reference_images"] = []
        payload["reference_image_assets"] = assets
        return payload

    def _deserialize_library_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        restored = dict(data)
        images: list[str] = []
        assets = restored.get("reference_image_assets", [])
        if isinstance(assets, list):
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                image_data = asset.get("data")
                if not isinstance(image_data, str) or not image_data:
                    continue
                try:
                    images.append(self._save_library_image_data(
                        base64.b64decode(image_data.encode("ascii")),
                        str(asset.get("suffix", ".png") or ".png"),
                    ))
                except (OSError, ValueError):
                    continue
        restored["reference_images"] = images
        return restored

    def _save_library_image_data(self, image_bytes: bytes, suffix: str) -> str:
        target_name = f"{uuid.uuid4().hex}{suffix or '.png'}"
        target_path = self._paths.library_images_dir / target_name
        target_path.write_bytes(image_bytes)
        return str(target_path)
