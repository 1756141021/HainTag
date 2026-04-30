from __future__ import annotations

import json
from datetime import datetime, timedelta

from ._paths import StoragePaths

_MAX_HISTORY = 500


class HistoryStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def _history_path(self):
        return self._paths.app_dir / "history.json"

    @staticmethod
    def _sort_key(entry) -> tuple[int, str]:
        timestamp = str(getattr(entry, "timestamp", "") or "")
        try:
            dt = datetime.fromisoformat(timestamp)
            return (1, dt.isoformat())
        except ValueError:
            return (0, timestamp)

    @staticmethod
    def _cleanup(entries: list, retention_days: int) -> list:
        ordered = sorted(entries, key=HistoryStorage._sort_key, reverse=True)
        if retention_days > 0:
            cutoff = datetime.now() - timedelta(days=retention_days)
            kept = []
            for entry in ordered:
                timestamp = str(getattr(entry, "timestamp", "") or "")
                try:
                    if datetime.fromisoformat(timestamp) < cutoff:
                        continue
                except ValueError:
                    pass
                kept.append(entry)
            ordered = kept
        return ordered[:_MAX_HISTORY]

    def load_history(self, retention_days: int = 0) -> list:
        from ..models import HistoryEntry
        path = self._history_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            entries = [HistoryEntry.from_dict(d) for d in data if isinstance(d, dict)]
            cleaned = self._cleanup(entries, retention_days)
            if len(cleaned) != len(entries):
                self.save_history(cleaned, retention_days=0)
            return cleaned
        except (OSError, json.JSONDecodeError):
            return []

    def save_history(self, entries: list, retention_days: int = 0) -> None:
        capped = self._cleanup(entries, retention_days)
        payload = json.dumps([e.to_dict() for e in capped], ensure_ascii=False, indent=2)
        self._history_path().write_text(payload, encoding="utf-8")

    def append_history(self, entry, retention_days: int = 0) -> None:
        entries = self.load_history(retention_days=0)
        entries.insert(0, entry)
        self.save_history(entries, retention_days=retention_days)

    def clear_history(self) -> None:
        path = self._history_path()
        if path.exists():
            path.unlink(missing_ok=True)
