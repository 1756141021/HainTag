from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
