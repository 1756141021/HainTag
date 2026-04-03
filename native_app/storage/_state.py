from __future__ import annotations

import json

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
        self._paths.settings_path.write_text(payload, encoding="utf-8")
