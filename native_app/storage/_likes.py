from __future__ import annotations

import json

from ._paths import StoragePaths


class LikesStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def _likes_path(self):
        return self._paths.app_dir / "likes.json"

    def load_likes(self) -> set[str]:
        path = self._likes_path()
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return set(data) if isinstance(data, list) else set()
        except (OSError, json.JSONDecodeError):
            return set()

    def save_likes(self, likes: set[str]) -> None:
        payload = json.dumps(sorted(likes), ensure_ascii=False, indent=2)
        self._likes_path().write_text(payload, encoding="utf-8")
