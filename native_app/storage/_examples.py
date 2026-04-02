from __future__ import annotations

import base64
import shutil
import uuid
from pathlib import Path
from typing import Any

from ..models import ExampleEntry
from ._paths import StoragePaths


class ExampleStorage:
    def __init__(self, paths: StoragePaths) -> None:
        self._paths = paths

    def copy_example_image(self, source_path: str) -> str:
        suffix = Path(source_path).suffix.lower() or ".png"
        target_name = f"{uuid.uuid4().hex}{suffix}"
        target_path = self._paths.examples_dir / target_name
        shutil.copy2(source_path, target_path)
        return str(target_path)

    def save_example_image_data(self, image_bytes: bytes, suffix: str) -> str:
        target_name = f"{uuid.uuid4().hex}{suffix or '.png'}"
        target_path = self._paths.examples_dir / target_name
        target_path.write_bytes(image_bytes)
        return str(target_path)

    def remove_example_image(self, image_path: str) -> None:
        if not image_path:
            return
        try:
            path = Path(image_path)
            if path.exists() and self._paths.examples_dir in path.parents:
                path.unlink()
        except OSError:
            return

    def serialize_example_entry(self, entry: ExampleEntry) -> dict[str, Any]:
        payload = entry.to_dict()
        image_path = Path(entry.image_path) if entry.image_path else None
        if image_path is not None and image_path.exists():
            payload["image_suffix"] = image_path.suffix.lower() or ".png"
            payload["image_data"] = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload["image_path"] = ""
        return payload

    def deserialize_example_entry(self, data: dict[str, Any]) -> ExampleEntry:
        restored = dict(data)
        restored_image = ""
        image_data = restored.get("image_data")
        if isinstance(image_data, str) and image_data:
            try:
                restored_image = self.save_example_image_data(
                    base64.b64decode(image_data.encode("ascii")),
                    str(restored.get("image_suffix", ".png") or ".png"),
                )
            except (OSError, ValueError):
                restored_image = ""
        restored["image_path"] = restored_image
        return ExampleEntry.from_dict(restored)
