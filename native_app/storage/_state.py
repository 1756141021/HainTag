from __future__ import annotations

import json
import os
import time

from .. import secret_store
from ..models import AppState
from ._paths import StoragePaths

_SECRET_FIELDS = ("api_key", "tagger_llm_api_key")


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
        self._restore_secrets(data)
        return AppState.from_dict(data)

    @staticmethod
    def _restore_secrets(data: dict) -> None:
        """Fill empty key fields from the OS credential store.

        Non-empty JSON values win (legacy plaintext or a hand-edited file);
        the next save migrates them into the store.
        """
        settings = data.get("settings")
        if not isinstance(settings, dict):
            return
        for field in _SECRET_FIELDS:
            if str(settings.get(field, "") or "").strip():
                continue
            stored = secret_store.get_secret(field)
            if stored:
                settings[field] = stored

    @staticmethod
    def _stash_secrets(data: dict) -> None:
        """Move key fields into the OS credential store, blanking them on disk.

        Store write failure keeps the plaintext value (fallback). An emptied
        key deletes the stored entry so it cannot resurrect on next load.
        """
        settings = data.get("settings")
        if not isinstance(settings, dict):
            return
        for field in _SECRET_FIELDS:
            value = str(settings.get(field, "") or "")
            if value.strip():
                if secret_store.set_secret(field, value):
                    settings[field] = ""
            else:
                secret_store.delete_secret(field)

    def save_state(self, state: AppState) -> None:
        data = state.to_dict()
        self._stash_secrets(data)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
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
