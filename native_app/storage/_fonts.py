from __future__ import annotations

import base64
import json
import shutil
import uuid

from ..models import AppSettings
from ._paths import StoragePaths


class FontStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def _font_index_path(self):
        return self._paths.fonts_dir / "index.json"

    def _load_font_index(self) -> list[dict]:
        path = self._font_index_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_font_index(self, index: list[dict]) -> None:
        self._font_index_path().write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    def import_font(self, source_path: str, family: str) -> tuple[str, str]:
        font_id = uuid.uuid4().hex
        filename = f"{font_id}.ttf"
        shutil.copy2(source_path, self._paths.fonts_dir / filename)
        index = self._load_font_index()
        index.append({"id": font_id, "filename": filename, "family": family})
        self._save_font_index(index)
        return font_id, family

    def list_imported_fonts(self) -> list[dict]:
        return self._load_font_index()

    def _find_font_entry(self, font_id: str) -> dict | None:
        for item in self._load_font_index():
            if item.get("id") == font_id:
                return item
        return None

    def font_file_path(self, font_id: str):
        from pathlib import Path
        entry = self._find_font_entry(font_id)
        if entry is None:
            return None
        filename = entry.get("filename", "")
        if not filename:
            return None
        path = self._paths.fonts_dir / filename
        return path if path.exists() else None

    def font_family_by_id(self, font_id: str) -> str:
        entry = self._find_font_entry(font_id)
        return entry.get("family", "") if entry else ""

    def _font_exists(self, font_id: str) -> bool:
        return self.font_file_path(font_id) is not None

    def serialize_font_assets(self, settings: AppSettings) -> list[dict]:
        if settings.font_profile != "custom" or not settings.custom_font_id:
            return []
        path = self.font_file_path(settings.custom_font_id)
        if path is None:
            return []
        index = self._load_font_index()
        for item in index:
            if item.get("id") == settings.custom_font_id:
                return [{
                    "id": item.get("id", ""),
                    "filename": item.get("filename", ""),
                    "family": item.get("family", ""),
                    "data_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
                }]
        return []

    def deserialize_font_assets(self, assets: list[dict]) -> None:
        index = self._load_font_index()
        existing_ids = {item.get("id", "") for item in index}
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            font_id = asset.get("id", "")
            data_b64 = asset.get("data_base64", "")
            family = asset.get("family", "")
            if not font_id or not data_b64:
                continue
            if font_id in existing_ids:
                continue
            filename = f"{font_id}.ttf"
            try:
                (self._paths.fonts_dir / filename).write_bytes(base64.b64decode(data_b64.encode("ascii")))
            except (OSError, ValueError):
                continue
            index.append({"id": font_id, "filename": filename, "family": family})
            existing_ids.add(font_id)
        self._save_font_index(index)

    def load_imported_fonts(self) -> list[str]:
        from PyQt6.QtGui import QFontDatabase
        families: list[str] = []
        for item in self._load_font_index():
            path = self._paths.fonts_dir / item.get("filename", "")
            if not path.exists():
                continue
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid >= 0:
                families.extend(QFontDatabase.applicationFontFamilies(fid))
        return families
