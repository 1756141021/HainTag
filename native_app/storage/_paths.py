from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoragePaths:
    app_dir: Path
    examples_dir: Path
    reports_dir: Path
    fonts_dir: Path
    library_images_dir: Path
    settings_path: Path

    @classmethod
    def from_app_dir(cls, app_dir: Path) -> StoragePaths:
        return cls(
            app_dir=app_dir,
            examples_dir=app_dir / "examples",
            reports_dir=app_dir / "reports",
            fonts_dir=app_dir / "fonts",
            library_images_dir=app_dir / "library_images",
            settings_path=app_dir / "settings.json",
        )

    def ensure_directories(self) -> None:
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.examples_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.library_images_dir.mkdir(parents=True, exist_ok=True)
