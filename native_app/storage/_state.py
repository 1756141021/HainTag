from __future__ import annotations

import json
import os
import time

from ..models import AppState
from ._paths import StoragePaths


class StateStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def load_state(self) -> AppState:
        if not self._paths.settings_path.exists():
            return AppState.default()
        try:
            data = json.loads(self._paths.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppState.default()
        return AppState.from_dict(data)

    def save_state(self, state: AppState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        target = self._paths.settings_path
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(f"{target.name}.tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        # Windows: settings.json may be transiently locked by AV / sync tools.
        # Retry the atomic rename a few times before giving up.
        last_error: Exception | None = None
        for delay in (0, 0.05, 0.15, 0.4):
            if delay:
                time.sleep(delay)
            try:
                os.replace(tmp_path, target)
                return
            except PermissionError as exc:
                last_error = exc
        # Final fallback: write directly (loses atomicity but keeps the data).
        try:
            target.write_text(payload, encoding="utf-8")
        except OSError:
            pass
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if last_error is not None and not target.exists():
            raise last_error
