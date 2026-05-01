from __future__ import annotations

import json
import os

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
        os.replace(tmp_path, target)
