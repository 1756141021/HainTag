"""LLM tagger processing logic — prompt presets, tag parsing, validation."""
from __future__ import annotations

import base64
import re
from pathlib import Path

from .models import ParsedTag
from .tag_dictionary import TagDictionary



def parse_llm_tags(raw_text: str) -> list[str]:
    """Parse LLM output into individual tag strings."""
    text = raw_text.strip()
    if not text:
        return []

    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]

    tags = [_normalize_tag(t) for t in text.split(",")]
    tags = [t for t in tags if t and not t.startswith("#")]

    if len(tags) < 3:
        tags = [_normalize_tag(t) for t in text.split("\n")]
        tags = [t for t in tags if t and not t.startswith("#")]

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


def _normalize_tag(raw: str) -> str:
    t = raw.strip().lower().replace(" ", "_")
    t = re.sub(r"^[\d\.\-\)\]\*]+\s*", "", t)
    t = t.strip("_").strip()
    return t


def validate_tags(
    tags: list[str], dictionary: TagDictionary | None
) -> list[ParsedTag]:
    """Validate tags against dictionary, fill category + translation."""
    result: list[ParsedTag] = []
    for tag_name in tags:
        if dictionary is not None:
            info = dictionary.lookup(tag_name)
            if info is not None:
                result.append(ParsedTag(
                    name=info.name,
                    is_valid=True,
                    category_id=info.category_id,
                    translation=info.translation,
                ))
                continue
        result.append(ParsedTag(name=tag_name, is_valid=False))
    return result


def build_vision_messages(image_path: str, prompt_text: str) -> list[dict]:
    """Build OpenAI-compatible vision messages with base64 image."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    ext = Path(image_path).suffix.lower().lstrip(".")
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }
    mime = mime_map.get(ext, "image/png")

    return [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": prompt_text},
        ],
    }]
