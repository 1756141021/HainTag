from __future__ import annotations

import io
from collections import OrderedDict
from queue import Queue, Empty
from threading import Lock

from PyQt6.QtCore import QThread, pyqtSignal, QSize, Qt
from PyQt6.QtGui import QImage, QPixmap


class ThumbLoaderThread(QThread):
    """Background thread that loads thumbnails using PIL for fast downsampling."""

    thumbnail_ready = pyqtSignal(str, int, QPixmap)  # path, requested_size, pixmap

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._queue: Queue[tuple[str, int]] = Queue()
        self._running = True
        self._seen: set[str] = set()  # dedup within current batch

    def request(self, path: str, size: int) -> None:
        key = f"{path}:{size}"
        if key not in self._seen:
            self._seen.add(key)
            self._queue.put((path, size))

    def cancel_pending(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Empty:
                break
        self._seen.clear()

    def run(self) -> None:
        while self._running:
            try:
                path, size = self._queue.get(timeout=0.1)
            except Empty:
                continue
            self._seen.discard(f"{path}:{size}")
            try:
                pixmap = self._load_fast(path, size)
                if pixmap and not pixmap.isNull():
                    self.thumbnail_ready.emit(path, size, pixmap)
            except Exception:
                pass

    def _load_fast(self, path: str, size: int) -> QPixmap | None:
        """Load thumbnail using PIL draft mode for fast downsampling."""
        try:
            from PIL import Image

            img = Image.open(path)
            # Draft mode: tells PIL to load at reduced resolution
            # Only works for JPEG; for PNG it still loads full but
            # PIL resize is faster than QPixmap.scaled for large images
            if hasattr(img, 'draft'):
                try:
                    img.draft("RGB", (size * 2, size * 2))
                except Exception:
                    pass

            # Fast thumbnail — modifies in-place, very efficient
            img.thumbnail((size, size), Image.Resampling.LANCZOS)

            # Convert to QPixmap via QImage with correct stride
            if img.mode == "RGBA":
                data = img.tobytes("raw", "BGRA")
                bpl = img.width * 4
                fmt = QImage.Format.Format_ARGB32
            else:
                img = img.convert("RGB")
                data = img.tobytes("raw", "RGB")
                bpl = img.width * 3
                fmt = QImage.Format.Format_RGB888

            qimg = QImage(data, img.width, img.height, bpl, fmt)
            return QPixmap.fromImage(qimg.copy())

        except Exception:
            # Fallback to QPixmap if PIL fails
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                return pixmap.scaled(
                    QSize(size, size),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            return None

    def stop(self) -> None:
        self._running = False
        self.cancel_pending()
        self.wait(3000)


class ThumbCache:
    """In-memory LRU cache for thumbnail QPixmaps.

    Thread-safe. Uses 2 loader threads for parallel thumbnail generation.
    """

    def __init__(self, max_size: int = 500) -> None:
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._max_size = max_size
        self._lock = Lock()
        self._pending: set[str] = set()
        self._callbacks: dict[str, list] = {}

        # Two loader threads for parallel loading
        self._loaders: list[ThumbLoaderThread] = []
        for _ in range(2):
            loader = ThumbLoaderThread()
            loader.thumbnail_ready.connect(self._on_loaded)
            loader.start()
            self._loaders.append(loader)
        self._loader_idx = 0

    def get(self, path: str, size: int = 160) -> QPixmap | None:
        key = f"{path}:{size}"
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def get_any(self, path: str) -> QPixmap | None:
        """Get any cached thumbnail for this path, regardless of size."""
        with self._lock:
            for key, pm in reversed(self._cache.items()):
                if key.startswith(path + ":"):
                    return pm
        return None

    def request(self, path: str, size: int, callback=None) -> None:
        """Request a thumbnail. Calls callback(path, pixmap) when ready."""
        key = f"{path}:{size}"
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                if callback:
                    callback(path, self._cache[key])
                return
            if key in self._pending:
                if callback:
                    self._callbacks.setdefault(key, []).append(callback)
                return
            self._pending.add(key)
            if callback:
                self._callbacks.setdefault(key, []).append(callback)
        # Round-robin between loaders
        self._loaders[self._loader_idx % len(self._loaders)].request(path, size)
        self._loader_idx += 1

    def _on_loaded(self, path: str, size: int, pixmap: QPixmap) -> None:
        key = f"{path}:{size}"
        with self._lock:
            self._cache[key] = pixmap
            self._cache.move_to_end(key)
            self._pending.discard(key)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
            cbs = self._callbacks.pop(key, [])
        for cb in cbs:
            cb(path, pixmap)

    def cancel_pending(self) -> None:
        for loader in self._loaders:
            loader.cancel_pending()
        with self._lock:
            self._pending.clear()
            self._callbacks.clear()

    def clear(self) -> None:
        self.cancel_pending()
        with self._lock:
            self._cache.clear()

    def stop(self) -> None:
        for loader in self._loaders:
            loader.stop()
