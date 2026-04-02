from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..models import (
    AppSettings,
    AppState,
    ConfigBundle,
    DockState,
    ErrorReport,
    ExampleEntry,
    PromptEntry,
    WidgetState,
    WindowState,
)
from ._config_bundle import ConfigBundleStorage
from ._error_reports import ErrorReportStorage
from ._examples import ExampleStorage
from ._fonts import FontStorage
from ._hints import HintsStorage
from ._history import HistoryStorage
from ._library import LibraryStorage
from ._likes import LikesStorage
from ._paths import StoragePaths
from ._prompts import PromptStorage
from ._state import StateStorage


class AppStorage:
    def __init__(self, app_name: str = "HainTag") -> None:
        appdata_root = os.environ.get("APPDATA")
        base_path = Path(appdata_root) if appdata_root else Path.home() / "AppData" / "Roaming"
        self._init_paths(base_path / app_name)

    def _init_paths(self, app_dir: Path) -> None:
        self._paths = StoragePaths.from_app_dir(app_dir)
        try:
            self._paths.ensure_directories()
        except PermissionError:
            fallback_root = Path.cwd() / ".native_appdata"
            self._paths = StoragePaths.from_app_dir(fallback_root / app_dir.name)
            self._paths.ensure_directories()

        self._state = StateStorage(self._paths)
        self._likes = LikesStorage(self._paths)
        self._hints = HintsStorage(self._paths)
        self._library = LibraryStorage(self._paths)
        self._history = HistoryStorage(self._paths)
        self._fonts = FontStorage(self._paths)
        self._examples = ExampleStorage(self._paths)
        self._prompts = PromptStorage()
        self._error_reports = ErrorReportStorage(self._paths)
        self._config_bundles = ConfigBundleStorage(self._paths, self._fonts, self._examples)

    # ── Path properties (backward compatibility) ──

    @property
    def app_dir(self) -> Path:
        return self._paths.app_dir

    @property
    def examples_dir(self) -> Path:
        return self._paths.examples_dir

    @property
    def reports_dir(self) -> Path:
        return self._paths.reports_dir

    @property
    def fonts_dir(self) -> Path:
        return self._paths.fonts_dir

    @property
    def library_images_dir(self) -> Path:
        return self._paths.library_images_dir

    @property
    def settings_path(self) -> Path:
        return self._paths.settings_path

    # ── State ──

    def load_state(self) -> AppState:
        return self._state.load_state()

    def save_state(self, state: AppState) -> None:
        self._state.save_state(state)

    # ── Likes ──

    def load_likes(self) -> set[str]:
        return self._likes.load_likes()

    def save_likes(self, likes: set[str]) -> None:
        self._likes.save_likes(likes)

    # ── Hints ──

    def load_shown_hints(self) -> set[str]:
        return self._hints.load_shown_hints()

    def save_shown_hints(self, hints: set[str]) -> None:
        self._hints.save_shown_hints(hints)

    # ── Library ──

    def load_library(self) -> tuple[list, list]:
        return self._library.load_library()

    def save_library(self, artists: list, ocs: list) -> None:
        self._library.save_library(artists, ocs)

    def copy_library_image(self, source_path: str) -> str:
        return self._library.copy_library_image(source_path)

    def remove_library_image(self, image_path: str) -> None:
        self._library.remove_library_image(image_path)

    # ── History ──

    def load_history(self) -> list:
        return self._history.load_history()

    def save_history(self, entries: list) -> None:
        self._history.save_history(entries)

    def append_history(self, entry) -> None:
        self._history.append_history(entry)

    def clear_history(self) -> None:
        self._history.clear_history()

    # ── Fonts ──

    def import_font(self, source_path: str, family: str) -> tuple[str, str]:
        return self._fonts.import_font(source_path, family)

    def list_imported_fonts(self) -> list[dict]:
        return self._fonts.list_imported_fonts()

    def font_file_path(self, font_id: str) -> Path | None:
        return self._fonts.font_file_path(font_id)

    def font_family_by_id(self, font_id: str) -> str:
        return self._fonts.font_family_by_id(font_id)

    def load_imported_fonts(self) -> list[str]:
        return self._fonts.load_imported_fonts()

    # ── Examples ──

    def copy_example_image(self, source_path: str) -> str:
        return self._examples.copy_example_image(source_path)

    def save_example_image_data(self, image_bytes: bytes, suffix: str) -> str:
        return self._examples.save_example_image_data(image_bytes, suffix)

    def remove_example_image(self, image_path: str) -> None:
        self._examples.remove_example_image(image_path)

    # ── Prompts ──

    def export_prompts(self, prompts: list[PromptEntry], target_path: str) -> None:
        self._prompts.export_prompts(prompts, target_path)

    def import_prompts(self, source_path: str) -> list[PromptEntry]:
        return self._prompts.import_prompts(source_path)

    # ── Config Bundle ──

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
        self._config_bundles.export_config_bundle(
            target_path, scope, settings=settings, prompts=prompts,
            examples=examples, dock=dock, widgets=widgets, window=window,
        )

    def import_config_bundle(self, source_path: str) -> ConfigBundle:
        return self._config_bundles.import_config_bundle(source_path)

    def merged_settings_from_bundle(self, bundle: ConfigBundle, current: AppSettings) -> AppSettings:
        return self._config_bundles.merged_settings_from_bundle(bundle, current)

    def state_from_bundle(self, bundle: ConfigBundle, current_state: AppState) -> AppState:
        return self._config_bundles.state_from_bundle(bundle, current_state)

    # ── Error Reports ──

    def write_error_report(self, report: ErrorReport) -> ErrorReport:
        return self._error_reports.write_error_report(report)
