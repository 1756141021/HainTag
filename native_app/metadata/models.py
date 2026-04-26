from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re


class GeneratorType(str, Enum):
    A1111 = "a1111"
    COMFYUI = "comfyui"
    NOVELAI = "novelai"
    FOOOCUS = "fooocus"
    UNKNOWN = "unknown"


@dataclass
class ImageMetadata:
    """Parsed metadata from an AI-generated image."""

    generator: GeneratorType = GeneratorType.UNKNOWN
    positive_prompt: str = ""
    negative_prompt: str = ""
    parameters: dict[str, str] = field(default_factory=dict)
    loras: list[dict[str, str]] = field(default_factory=list)
    model_name: str = ""
    model_hash: str = ""
    raw_chunks: dict[str, str] = field(default_factory=dict)
    workflow_json: str = ""

    @property
    def has_content(self) -> bool:
        return bool(self.positive_prompt or self.negative_prompt or self.parameters)

    def parameter(self, key: str, default: str = "") -> str:
        return str(self.parameters.get(key, default) or default)

    def set_parameter(self, key: str, value: str | int | float | None) -> None:
        text = "" if value is None else str(value).strip()
        if text:
            self.parameters[key] = text
        else:
            self.parameters.pop(key, None)

    def size_tuple(self) -> tuple[int, int]:
        raw = self.parameter("Size")
        match = re.match(r"\s*(\d+)\s*x\s*(\d+)\s*$", raw, flags=re.IGNORECASE)
        if not match:
            return 0, 0
        return int(match.group(1)), int(match.group(2))

    def set_size(self, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self.parameters["Size"] = f"{int(width)}x{int(height)}"
        else:
            self.parameters.pop("Size", None)

    def sync_loras_to_positive_prompt(self) -> None:
        prompt = re.sub(r"\s*,?\s*<lora:[^:>]+:[^>]+>", "", self.positive_prompt).strip()
        lora_tags = []
        for item in self.loras:
            name = str(item.get("name", "")).strip()
            weight = str(item.get("weight", "")).strip() or "1"
            if name:
                lora_tags.append(f"<lora:{name}:{weight}>")
        if lora_tags:
            prompt = ", ".join(part for part in [prompt, *lora_tags] if part)
        self.positive_prompt = prompt
