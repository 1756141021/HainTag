"""cl_tagger ONNX inference engine — local Danbooru tag prediction."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

# ── Optional dependency check ──

_ONNX_AVAILABLE = False
_HF_AVAILABLE = False
_NUMPY_AVAILABLE = False

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None

try:
    from PIL import Image
except ImportError:
    Image = None

ort = None  # lazy import in TaggerEngine.load()

try:
    from huggingface_hub import hf_hub_download
    _HF_AVAILABLE = True
except ImportError:
    pass


REPO_ID = "cella110n/cl_tagger"
MODEL_SUBDIR = "cl_tagger_1_02"
MODEL_FILENAME = f"{MODEL_SUBDIR}/model_optimized.onnx"
MAPPING_FILENAME = f"{MODEL_SUBDIR}/tag_mapping.json"

# Category indices in tag_mapping.json
CATEGORY_NAMES = ["general", "character", "copyright", "meta", "model", "rating", "quality", "artist"]

DEFAULT_BLACKLIST = [
    "watermark", "sample watermark", "weibo", "weibo username", "weibo logo",
    "weibo watermark", "censored", "mosaic censoring", "artist name",
    "twitter username", "patreon username", "pixiv id", "signature",
]

DEFAULT_ENABLED_CATEGORIES = {"general", "character", "copyright"}


def is_local_tagger_available() -> bool:
    """Check if all deps are importable. Only used for UI hints, not as a gate."""
    try:
        import onnxruntime
        import numpy
        from PIL import Image as _
        return True
    except Exception:
        return False


def _pad_square(image: Image.Image) -> Image.Image:
    """Pad image to square with white background."""
    w, h = image.size
    if w == h:
        return image
    size = max(w, h)
    new_img = Image.new("RGB", (size, size), (255, 255, 255))
    new_img.paste(image, ((size - w) // 2, (size - h) // 2))
    return new_img


def _preprocess(image: Image.Image) -> np.ndarray:
    """Preprocess image for cl_tagger: RGB → pad → 448x448 → BGR → normalize → CHW → batch."""
    image = image.convert("RGB")
    image = _pad_square(image)
    image = image.resize((448, 448), Image.BICUBIC)
    arr = np.array(image, dtype=np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)  # HWC → CHW
    arr = arr[::-1, :, :]         # RGB → BGR
    arr = (arr - 0.5) / 0.5      # normalize mean=0.5, std=0.5
    return np.expand_dims(arr, 0).copy()  # batch, contiguous


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class TagMapping:
    """Parsed tag_mapping.json — maps indices to tag names and categories."""

    def __init__(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.names: list[str] = []
        self.categories: list[str] = []
        self.category_indices: dict[str, list[int]] = {c: [] for c in CATEGORY_NAMES}

        if isinstance(data, list):
            # List format: [{tag, category, ...}, ...]
            for i, entry in enumerate(data):
                name = entry.get("tag", entry.get("name", f"tag_{i}"))
                cat = entry.get("category", "general").lower()
                self.names.append(name)
                self.categories.append(cat)
                if cat in self.category_indices:
                    self.category_indices[cat].append(i)
        elif isinstance(data, dict):
            # Dict format: {"index": {"tag": "1girl", "category": "General"}, ...}
            for i, (key, info) in enumerate(data.items()):
                cat = (info.get("category", "general") if isinstance(info, dict) else "general").lower()
                name = info.get("tag", key) if isinstance(info, dict) else key
                self.names.append(name)
                self.categories.append(cat)
                if cat in self.category_indices:
                    self.category_indices[cat].append(i)

    def __len__(self) -> int:
        return len(self.names)


class TaggerEngine:
    """ONNX-based local image tagger using cl_tagger model.

    Supports two modes:
    - Direct: import onnxruntime in-process (fast, requires compatible Python)
    - Subprocess: call external Python with onnxruntime (slower, works with any Python)
    """

    def __init__(self, model_dir: str | None = None):
        self._session = None
        self._mapping: TagMapping | None = None
        self._model_dir = model_dir
        self._model_path: str | None = None
        self._mapping_path: str | None = None
        self._use_subprocess = False
        self._external_python: str | None = None

    @property
    def is_ready(self) -> bool:
        if self._use_subprocess:
            return self._model_path is not None and self._mapping_path is not None
        return self._session is not None and self._mapping is not None

    def model_paths(self, base_dir: str | None = None) -> tuple[str | None, str | None]:
        """Return (model_path, mapping_path) if found, else (None, None)."""
        if base_dir:
            model = os.path.join(base_dir, "model_optimized.onnx")
            mapping = os.path.join(base_dir, "tag_mapping.json")
            if os.path.isfile(model) and os.path.isfile(mapping):
                return model, mapping
        return None, None

    def find_model(self, custom_dir: str | None = None,
                   appdata_dir: str | None = None) -> tuple[str | None, str | None]:
        """Search for model files in custom dir, then appdata, then HF cache."""
        # 1. Custom directory
        if custom_dir:
            m, t = self.model_paths(custom_dir)
            if m:
                return m, t

        # 2. AppData models dir
        if appdata_dir:
            model_sub = os.path.join(appdata_dir, "models", MODEL_SUBDIR)
            m, t = self.model_paths(model_sub)
            if m:
                return m, t

        # 3. HuggingFace cache
        if _HF_AVAILABLE:
            try:
                from huggingface_hub import try_to_load_from_cache
                m = try_to_load_from_cache(REPO_ID, MODEL_FILENAME)
                t = try_to_load_from_cache(REPO_ID, MAPPING_FILENAME)
                if m and t and isinstance(m, str) and isinstance(t, str):
                    return m, t
            except Exception:
                pass

        return None, None

    def load(self, model_path: str, mapping_path: str,
             external_python: str | None = None) -> None:
        """Load ONNX model and tag mapping.

        Tries direct import first. If onnxruntime can't load, falls back to
        subprocess mode using external_python.
        """
        self._model_path = model_path
        self._mapping_path = mapping_path

        try:
            import onnxruntime as _ort
            opts = _ort.SessionOptions()
            opts.graph_optimization_level = _ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = _ort.InferenceSession(
                model_path, sess_options=opts, providers=["CPUExecutionProvider"]
            )
            self._mapping = TagMapping(mapping_path)
            self._use_subprocess = False
        except Exception:
            # Direct import failed — use subprocess mode
            if external_python:
                self._external_python = external_python
            else:
                # Auto-detect embedded Python environment
                from .python_env import get_embedded_python_path, is_env_usable
                embedded = get_embedded_python_path()
                if embedded and is_env_usable(embedded):
                    self._external_python = embedded
            self._use_subprocess = True
            self._mapping = TagMapping(mapping_path)  # still load mapping for category info

    def set_external_python(self, path: str) -> None:
        self._external_python = path

    def predict(
        self,
        image_path: str,
        gen_threshold: float = 0.35,
        char_threshold: float = 0.70,
        enabled_categories: set[str] | None = None,
        blacklist: list[str] | None = None,
    ) -> dict[str, list[tuple[str, float]]]:
        """Run inference and return tags grouped by category.

        Returns: {category: [(tag_name, probability), ...]}
        """
        if not self.is_ready:
            raise RuntimeError("Model not loaded")

        if self._use_subprocess:
            return self._predict_subprocess(image_path, gen_threshold, char_threshold,
                                            enabled_categories, blacklist)

        if enabled_categories is None:
            enabled_categories = DEFAULT_ENABLED_CATEGORIES
        if blacklist is None:
            blacklist = DEFAULT_BLACKLIST

        blacklist_set = set(blacklist)
        image = Image.open(image_path)
        input_tensor = _preprocess(image)

        input_name = self._session.get_inputs()[0].name
        output_name = self._session.get_outputs()[0].name
        outputs = self._session.run([output_name], {input_name: input_tensor})[0]
        probs = _sigmoid(outputs[0])

        results: dict[str, list[tuple[str, float]]] = {}

        for category in CATEGORY_NAMES:
            if category not in enabled_categories:
                continue

            indices = self._mapping.category_indices.get(category, [])
            if not indices:
                continue

            # Pick threshold
            if category in ("character", "copyright", "artist"):
                threshold = char_threshold
            elif category in ("rating", "quality"):
                threshold = 0.0  # always show best match
            else:
                threshold = gen_threshold

            entries = []
            for idx in indices:
                if idx >= len(probs):
                    continue
                prob = float(probs[idx])
                if prob < threshold:
                    continue
                name = self._mapping.names[idx]
                if name in blacklist_set:
                    continue
                entries.append((name, prob))

            # Rating/quality: only top-1
            if category in ("rating", "quality") and entries:
                entries = [max(entries, key=lambda x: x[1])]
            else:
                entries.sort(key=lambda x: x[1], reverse=True)

            if entries:
                results[category] = entries

        return results

    def _predict_subprocess(
        self,
        image_path: str,
        gen_threshold: float,
        char_threshold: float,
        enabled_categories: set[str] | None,
        blacklist: list[str] | None,
    ) -> dict[str, list[tuple[str, float]]]:
        """Run inference via external Python subprocess."""
        import json as _json
        import subprocess

        python = self._external_python
        if not python:
            raise RuntimeError("需要指定外部 Python 路径（如 ComfyUI 的 Python）")

        script = os.path.join(os.path.dirname(__file__), "tagger_subprocess.py")
        cats_str = ",".join(enabled_categories or DEFAULT_ENABLED_CATEGORIES)
        bl_str = ",".join(blacklist or DEFAULT_BLACKLIST)

        cmd = [
            python, script, image_path,
            self._model_path, self._mapping_path,
            str(gen_threshold), str(char_threshold),
            cats_str, bl_str,
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        if result.returncode != 0:
            raise RuntimeError(f"子进程错误: {result.stderr.strip()}")

        data = _json.loads(result.stdout.strip())
        if "error" in data:
            raise RuntimeError(data["error"])

        # Convert lists back to tuples
        return {
            cat: [(name, prob) for name, prob in entries]
            for cat, entries in data.get("results", {}).items()
        }


class TaggerDownloadWorker(QThread):
    """Background thread to download cl_tagger model from HuggingFace."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(str, str)  # model_path, mapping_path
    error = pyqtSignal(str)

    def __init__(self, target_dir: str | None = None, parent=None):
        super().__init__(parent)
        self._target_dir = target_dir

    def run(self):
        try:
            if not _HF_AVAILABLE:
                self.error.emit("huggingface_hub is not installed")
                return

            self.progress.emit("Downloading model (~1.4GB)...")
            if self._target_dir:
                cache_dir = self._target_dir
            else:
                cache_dir = None

            model_path = hf_hub_download(
                repo_id=REPO_ID, filename=MODEL_FILENAME,
                cache_dir=cache_dir, force_download=False
            )
            self.progress.emit("Downloading tag mapping...")
            mapping_path = hf_hub_download(
                repo_id=REPO_ID, filename=MAPPING_FILENAME,
                cache_dir=cache_dir, force_download=False
            )
            self.finished.emit(model_path, mapping_path)
        except Exception as exc:
            self.error.emit(str(exc))


class TaggerWorker(QThread):
    """Background thread for running tagger inference."""

    finished = pyqtSignal(dict)  # {category: [(tag, prob), ...]}
    error = pyqtSignal(str)

    def __init__(self, engine: TaggerEngine, image_path: str,
                 gen_threshold: float, char_threshold: float,
                 enabled_categories: set[str],
                 blacklist: list[str], parent=None):
        super().__init__(parent)
        self._engine = engine
        self._image_path = image_path
        self._gen_threshold = gen_threshold
        self._char_threshold = char_threshold
        self._enabled_categories = enabled_categories
        self._blacklist = blacklist

    def run(self):
        try:
            results = self._engine.predict(
                self._image_path,
                gen_threshold=self._gen_threshold,
                char_threshold=self._char_threshold,
                enabled_categories=self._enabled_categories,
                blacklist=self._blacklist,
            )
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))
