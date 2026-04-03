from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from ._paths import StoragePaths


class LibraryStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def _library_path(self):
        return self._paths.app_dir / "library.json"

    def load_library(self) -> tuple[list, list]:
        """Load artist and OC entries. Returns (artists, ocs)."""
        from ..models import ArtistEntry, OCEntry
        path = self._library_path()
        if not path.exists():
            return [], []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            artists = [ArtistEntry.from_dict(d) for d in data.get("artists", [])]
            ocs = [OCEntry.from_dict(d) for d in data.get("ocs", [])]
            return artists, ocs
        except (OSError, json.JSONDecodeError):
            return [], []

    def save_library(self, artists: list, ocs: list) -> None:
        payload = json.dumps({
            "artists": [a.to_dict() for a in artists],
            "ocs": [o.to_dict() for o in ocs],
        }, ensure_ascii=False, indent=2)
        self._library_path().write_text(payload, encoding="utf-8")

    def copy_library_image(self, source_path: str) -> str:
        """Copy an image to library_images dir. Returns the new path."""
        src = Path(source_path)
        dest = self._paths.library_images_dir / f"{uuid.uuid4().hex}{src.suffix}"
        shutil.copy2(src, dest)
        return str(dest)

    def remove_library_image(self, image_path: str) -> None:
        """Remove an image if it's inside library_images dir."""
        p = Path(image_path)
        if p.exists() and self._paths.library_images_dir in p.parents:
            p.unlink(missing_ok=True)
