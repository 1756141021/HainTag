from __future__ import annotations

import json

from ._paths import StoragePaths

_MAX_HISTORY = 500


class HistoryStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def _history_path(self):
        return self._paths.app_dir / "history.json"

    def load_history(self) -> list:
        from ..models import HistoryEntry
        path = self._history_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [HistoryEntry.from_dict(d) for d in data if isinstance(d, dict)]
        except (OSError, json.JSONDecodeError):
            return []

    def save_history(self, entries: list) -> None:
        capped = entries[:_MAX_HISTORY]
        payload = json.dumps([e.to_dict() for e in capped], ensure_ascii=False, indent=2)
        self._history_path().write_text(payload, encoding="utf-8")

    def append_history(self, entry) -> None:
        entries = self.load_history()
        entries.insert(0, entry)
        self.save_history(entries)

    def clear_history(self) -> None:
        path = self._history_path()
        if path.exists():
            path.unlink(missing_ok=True)
