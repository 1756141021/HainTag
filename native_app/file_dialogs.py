"""Centralized file-dialog helpers that remember last-used directories.

Each widget that opens a QFileDialog for image selection used to pass an empty
initial path, so the dialog defaulted to the process CWD. This module tracks a
single "last image directory" and seeds every image picker with it. The
MainWindow primes the cache from `_state.settings.image_manager_folder` at
startup; subsequent picks update the cache so the next dialog opens at the same
spot.
"""

from __future__ import annotations

import os
from typing import Sequence

from PyQt6.QtWidgets import QFileDialog, QWidget

from .file_filters import image_filter

_last_image_dir: str = ""


def set_last_image_dir(folder: str) -> None:
    """Seed the cache, e.g. from saved settings on startup."""
    global _last_image_dir
    if folder and os.path.isdir(folder):
        _last_image_dir = folder


def get_last_image_dir() -> str:
    return _last_image_dir


def _remember_dir_from_path(path: str) -> None:
    global _last_image_dir
    folder = os.path.dirname(path)
    if folder and os.path.isdir(folder):
        _last_image_dir = folder


def pick_image_file(
    parent: QWidget,
    translator,
    *,
    title_key: str = "select_image",
    initial_dir: str | None = None,
    include_gif: bool = False,
    all_files: bool = False,
) -> str:
    start = initial_dir if initial_dir is not None else _last_image_dir
    path, _ = QFileDialog.getOpenFileName(
        parent,
        translator.t(title_key),
        start,
        image_filter(translator, include_gif=include_gif, all_files=all_files),
    )
    if path:
        _remember_dir_from_path(path)
    return path


def pick_image_files(
    parent: QWidget,
    translator,
    *,
    title_key: str = "select_image",
    initial_dir: str | None = None,
    include_gif: bool = False,
    all_files: bool = False,
) -> list[str]:
    start = initial_dir if initial_dir is not None else _last_image_dir
    paths, _ = QFileDialog.getOpenFileNames(
        parent,
        translator.t(title_key),
        start,
        image_filter(translator, include_gif=include_gif, all_files=all_files),
    )
    if paths:
        _remember_dir_from_path(paths[0])
    return list(paths)
