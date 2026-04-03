from __future__ import annotations

import json

from ..models import GeneratorType, ImageMetadata
from .base import BaseMetadataParser


class FooocusParser(BaseMetadataParser):
    """Parser for Fooocus metadata.

    Fooocus stores a JSON object in a ``parameters`` or ``fooocus_scheme``
    tEXt chunk.  The JSON contains keys like ``prompt``, ``negative_prompt``,
    ``styles``, ``performance``, ``steps``, ``cfg``, ``base_model``, etc.
    """

    def can_parse(self, chunks: dict[str, str]) -> bool:
        # Fooocus uses "parameters" like A1111, but the content is JSON
        for key in ("fooocus_scheme", "parameters", "prompt"):
            text = chunks.get(key, "")
            if not text:
                continue
            try:
                data = json.loads(text)
                if isinstance(data, dict) and ("base_model" in data or "full_prompt" in data):
                    return True
            except (json.JSONDecodeError, TypeError):
                continue
        return False

    def parse(self, chunks: dict[str, str], image_path: str = "") -> ImageMetadata:
        data: dict = {}
        for key in ("fooocus_scheme", "parameters", "prompt"):
            text = chunks.get(key, "")
            if not text:
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    data = parsed
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        positive = data.get("prompt", data.get("full_prompt", ""))
        negative = data.get("negative_prompt", data.get("full_negative_prompt", ""))

        params: dict[str, str] = {}
        for key in ("steps", "cfg", "sampler", "scheduler", "seed",
                     "performance", "resolution", "sharpness"):
            val = data.get(key)
            if val is not None:
                params[key] = str(val)

        width = data.get("width")
        height = data.get("height")
        if width and height:
            params["size"] = f"{width}x{height}"

        model_name = data.get("base_model", data.get("base_model_name", ""))
        model_hash = data.get("base_model_hash", "")

        loras: list[dict[str, str]] = []
        for lora_info in data.get("loras", []):
            if isinstance(lora_info, dict):
                loras.append({
                    "name": str(lora_info.get("name", lora_info.get("model_name", ""))),
                    "weight": str(lora_info.get("weight", lora_info.get("strength_model", ""))),
                })
            elif isinstance(lora_info, (list, tuple)) and len(lora_info) >= 2:
                loras.append({"name": str(lora_info[0]), "weight": str(lora_info[1])})

        return ImageMetadata(
            generator=GeneratorType.FOOOCUS,
            positive_prompt=positive,
            negative_prompt=negative,
            parameters=params,
            loras=loras,
            model_name=model_name,
            model_hash=model_hash,
            raw_chunks=dict(chunks),
        )
