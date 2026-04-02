from __future__ import annotations

import json
import struct
import zlib

from ..models import GeneratorType, ImageMetadata
from .base import BaseMetadataParser


class NovelAIParser(BaseMetadataParser):
    """Parser for NovelAI metadata.

    NovelAI stores metadata in two possible ways:
    1. PNG tEXt chunks: ``Description`` (prompt), ``Comment`` (JSON with
       generation params including ``uc`` for negative prompt), ``Source``.
    2. Steganographic LSB encoding in the alpha channel (stealth pnginfo).
       Magic: ``stealth_pngcomp`` followed by gzip-compressed JSON.
    """

    def can_parse(self, chunks: dict[str, str]) -> bool:
        if chunks.get("Software", "").startswith("NovelAI"):
            return True
        if "Comment" in chunks and "Description" in chunks:
            try:
                comment = json.loads(chunks["Comment"])
                return isinstance(comment, dict) and "uc" in comment
            except (json.JSONDecodeError, TypeError):
                pass
        return False

    def parse(self, chunks: dict[str, str], image_path: str = "") -> ImageMetadata:
        positive = chunks.get("Description", "")
        negative = ""
        params: dict[str, str] = {}
        model_name = ""

        comment_str = chunks.get("Comment", "")
        if comment_str:
            try:
                comment = json.loads(comment_str)
                if isinstance(comment, dict):
                    negative = comment.get("uc", "")
                    for key in ("steps", "scale", "seed", "sampler", "strength", "noise"):
                        val = comment.get(key)
                        if val is not None:
                            params[key] = str(val)
                    # NovelAI uses "scale" for CFG
                    if "scale" in params:
                        params["cfg_scale"] = params.pop("scale")
            except (json.JSONDecodeError, TypeError):
                pass

        # If no text chunks found, try steganographic extraction
        if not positive and not negative and image_path:
            stealth = self._extract_stealth(image_path)
            if stealth:
                positive = stealth.get("Description", "")
                comment = stealth.get("Comment")
                if isinstance(comment, str):
                    try:
                        comment = json.loads(comment)
                    except (json.JSONDecodeError, TypeError):
                        comment = None
                if isinstance(comment, dict):
                    negative = comment.get("uc", "")
                    for key in ("steps", "scale", "seed", "sampler"):
                        val = comment.get(key)
                        if val is not None:
                            params[key] = str(val)
                    if "scale" in params:
                        params["cfg_scale"] = params.pop("scale")

        return ImageMetadata(
            generator=GeneratorType.NOVELAI,
            positive_prompt=positive,
            negative_prompt=negative,
            parameters=params,
            model_name=model_name,
            raw_chunks=dict(chunks),
        )

    @staticmethod
    def _extract_stealth(image_path: str) -> dict | None:
        """Extract metadata hidden in alpha channel LSBs.

        NovelAI stealth pnginfo encodes data as:
        - Magic: "stealth_pngcomp" (read from LSBs, column-major order)
        - 32-bit big-endian length
        - gzip-compressed JSON payload
        """
        try:
            from PIL import Image
        except ImportError:
            return None

        try:
            img = Image.open(image_path)
            if img.mode != "RGBA":
                return None

            pixels = img.load()
            width, height = img.size

            # Read bits from alpha channel LSBs (column-major: x outer, y inner)
            bits: list[int] = []
            for x in range(width):
                for y in range(height):
                    alpha = pixels[x, y][3]
                    bits.append(alpha & 1)

            # Convert bits to bytes
            def bits_to_bytes(bit_list: list[int]) -> bytes:
                result = bytearray()
                for i in range(0, len(bit_list), 8):
                    byte = 0
                    for j in range(8):
                        if i + j < len(bit_list):
                            byte = (byte << 1) | bit_list[i + j]
                    result.append(byte)
                return bytes(result)

            # Check magic
            magic = "stealth_pngcomp"
            magic_bits = len(magic) * 8
            if len(bits) < magic_bits + 32:
                return None

            magic_bytes = bits_to_bytes(bits[:magic_bits])
            if magic_bytes.decode("ascii", errors="replace") != magic:
                return None

            # Read length (32-bit, after magic)
            length_bits = bits[magic_bits:magic_bits + 32]
            length = 0
            for b in length_bits:
                length = (length << 1) | b

            # Read payload
            payload_start = magic_bits + 32
            if len(bits) < payload_start + length:
                return None
            payload_bytes = bits_to_bytes(bits[payload_start:payload_start + length])

            # Decompress
            decompressed = zlib.decompress(payload_bytes)
            text = decompressed.decode("utf-8")

            # Parse as JSON or as key-value chunks
            try:
                result = json.loads(text)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

            # Try parsing as newline-separated key: value
            result = {}
            for line in text.split("\n"):
                if ": " in line:
                    key, _, val = line.partition(": ")
                    result[key.strip()] = val.strip()
            return result if result else None

        except Exception:
            return None
