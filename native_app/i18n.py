from __future__ import annotations

import json
from pathlib import Path


class Translator:
    def __init__(self, resources_dir: Path, default_language: str = "zh-CN") -> None:
        self._resources_dir = resources_dir
        self._fallback = "en"
        self._catalogs: dict[str, dict[str, str]] = {}
        self._language = default_language
        self._load_catalogs()

    def _load_catalogs(self) -> None:
        lang_dir = self._resources_dir / "lang"
        for path in lang_dir.glob("*.json"):
            try:
                self._catalogs[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
        if self._fallback not in self._catalogs:
            self._catalogs[self._fallback] = {}
        if self._language not in self._catalogs:
            self._language = self._fallback

    def set_language(self, language: str) -> None:
        if language in self._catalogs:
            self._language = language

    def get_language(self) -> str:
        return self._language

    def available_languages(self) -> list[str]:
        return sorted(self._catalogs)

    def t(self, key: str) -> str:
        return (
            self._catalogs.get(self._language, {}).get(key)
            or self._catalogs.get(self._fallback, {}).get(key)
            or key
        )
