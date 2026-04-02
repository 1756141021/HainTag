from __future__ import annotations

import json

from ._paths import StoragePaths


class HintsStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def _hints_path(self):
        return self._paths.app_dir / "hints.json"

    def load_shown_hints(self) -> set[str]:
        path = self._hints_path()
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return set(data) if isinstance(data, list) else set()
        except (OSError, json.JSONDecodeError):
            return set()

    def save_shown_hints(self, hints: set[str]) -> None:
        payload = json.dumps(sorted(hints), ensure_ascii=False, indent=2)
        self._hints_path().write_text(payload, encoding="utf-8")
