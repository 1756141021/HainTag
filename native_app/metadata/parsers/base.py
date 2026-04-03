from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ImageMetadata


class BaseMetadataParser(ABC):
    """Abstract base for metadata parsers.

    Each parser targets a specific AI image generator format.
    ``can_parse`` inspects the raw PNG text chunks (keyword → value)
    and returns *True* if this parser recognises the format.
    ``parse`` then converts those chunks into a structured
    :class:`ImageMetadata`.
    """

    @abstractmethod
    def can_parse(self, chunks: dict[str, str]) -> bool:
        ...

    @abstractmethod
    def parse(self, chunks: dict[str, str], image_path: str = "") -> ImageMetadata:
        ...
