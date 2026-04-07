from __future__ import annotations

import os
import re
import struct
import zlib
from typing import BinaryIO

from .models import GeneratorType, ImageMetadata

# PNG signature: 8 bytes
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Chunk types that carry text metadata
_TEXT_CHUNK_TYPES = {b"tEXt", b"iTXt", b"zTXt"}

# 销毁时注入的垃圾文本
_DESTROY_TEXT = "哈基米哦南北绿豆~阿西嘎哈椰果奶龙~"


class MetadataWriter:
    """Binary-level PNG chunk manipulation.

    All operations produce a **copy** — the source file is never modified.
    IDAT chunks (image data) are copied byte-for-byte, ensuring zero
    quality loss.
    """

    def write_chunks(
        self,
        src: str,
        dst: str,
        new_text_chunks: dict[str, str],
    ) -> None:
        """Replace all tEXt/iTXt/zTXt chunks with *new_text_chunks*.

        IDAT and all non-text chunks are preserved verbatim.
        """
        raw_chunks = self._read_raw_chunks(src)

        with open(dst, "wb") as f:
            f.write(_PNG_SIGNATURE)

            # Write IHDR first (must always be first)
            for chunk_type, chunk_data in raw_chunks:
                if chunk_type == b"IHDR":
                    self._write_chunk(f, chunk_type, chunk_data)
                    break

            # Write new text chunks (after IHDR, before IDAT)
            for keyword, text in new_text_chunks.items():
                self._write_text_chunk(f, keyword, text)

            # Write all non-text, non-IHDR, non-IEND chunks (preserves IDAT verbatim)
            for chunk_type, chunk_data in raw_chunks:
                if chunk_type == b"IHDR":
                    continue
                if chunk_type == b"IEND":
                    continue
                if chunk_type in _TEXT_CHUNK_TYPES:
                    continue
                self._write_chunk(f, chunk_type, chunk_data)

            # Write IEND
            self._write_chunk(f, b"IEND", b"")

    def destroy(self, src: str, dst: str, text: str | None = None) -> None:
        """Destroy metadata by overwriting all text chunks with garbage.

        Writes in standard A1111 format so tools display: positive prompt
        = garbage text, negative = garbage text, Steps: 0.
        IDAT is byte-for-byte identical to the source.
        """
        fill = text if text is not None else _DESTROY_TEXT
        fake_params = (
            f"{fill}\n"
            f"Negative prompt: {fill}\n"
            f"Steps: 0, Sampler: {fill}, CFG scale: 0, "
            f"Seed: 0, Size: 0x0, Model: {fill}"
        )
        self.write_chunks(src, dst, {"parameters": fake_params})

    def edit(self, src: str, dst: str, metadata: ImageMetadata) -> None:
        """Edit metadata by writing structured content back.

        Serialises *metadata* into the format matching its generator type,
        then writes those chunks.  IDAT is byte-for-byte identical.
        """
        chunks = self._serialize_metadata(metadata)
        self.write_chunks(src, dst, chunks)

    def strip_stealth(self, src: str, dst: str) -> None:
        """Clear NovelAI stealth metadata from the alpha channel.

        This DOES re-encode IDAT (unavoidable when modifying pixel data),
        but PNG is lossless so image quality is preserved.
        """
        try:
            from PIL import Image

            img = Image.open(src)
            if img.mode != "RGBA":
                # No alpha channel, just copy
                import shutil
                shutil.copy2(src, dst)
                return

            pixels = img.load()
            width, height = img.size

            # Clear LSB of all alpha values
            for x in range(width):
                for y in range(height):
                    r, g, b, a = pixels[x, y]
                    pixels[x, y] = (r, g, b, a & 0xFE)

            img.save(dst, "PNG")
            img.close()
        except Exception:
            import shutil
            shutil.copy2(src, dst)

    # ── Internal helpers ──

    @staticmethod
    def _read_raw_chunks(path: str) -> list[tuple[bytes, bytes]]:
        """Read all PNG chunks as (type, data) pairs, excluding the signature."""
        chunks: list[tuple[bytes, bytes]] = []
        with open(path, "rb") as f:
            sig = f.read(8)
            if sig != _PNG_SIGNATURE:
                raise ValueError(f"Not a valid PNG file: {path}")

            while True:
                length_bytes = f.read(4)
                if len(length_bytes) < 4:
                    break
                length = struct.unpack(">I", length_bytes)[0]
                chunk_type = f.read(4)
                chunk_data = f.read(length)
                crc = f.read(4)  # CRC covers type + data
                chunks.append((chunk_type, chunk_data))

        return chunks

    @staticmethod
    def _write_chunk(f: BinaryIO, chunk_type: bytes, data: bytes) -> None:
        """Write a single PNG chunk with correct length and CRC."""
        f.write(struct.pack(">I", len(data)))
        f.write(chunk_type)
        f.write(data)
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        f.write(struct.pack(">I", crc))

    @staticmethod
    def _write_text_chunk(f: BinaryIO, keyword: str, text: str) -> None:
        """Write a text chunk, auto-selecting tEXt or iTXt.

        Latin-1 encodable text → tEXt (maximum compatibility).
        Non-Latin-1 text (CJK, emoji, etc.) → iTXt (correct UTF-8).
        This matches Pillow's add_text() behavior used by A1111/ComfyUI.
        """
        keyword_bytes = keyword.encode("latin-1", errors="replace")
        try:
            text_bytes = text.encode("latin-1", errors="strict")
            # Latin-1 safe → tEXt
            data = keyword_bytes + b"\x00" + text_bytes
            MetadataWriter._write_chunk(f, b"tEXt", data)
        except UnicodeEncodeError:
            # Non-Latin-1 → iTXt (uncompressed)
            # Format: keyword \0 compression_flag \0 compression_method \0
            #         language_tag \0 translated_keyword \0 text_utf8
            text_bytes = text.encode("utf-8")
            data = keyword_bytes + b"\x00\x00\x00\x00\x00" + text_bytes
            MetadataWriter._write_chunk(f, b"iTXt", data)

    @staticmethod
    def _serialize_metadata(metadata: ImageMetadata) -> dict[str, str]:
        """Serialize ImageMetadata back into PNG text chunk key-value pairs."""
        if metadata.generator == GeneratorType.A1111:
            return MetadataWriter._serialize_a1111(metadata)
        elif metadata.generator == GeneratorType.COMFYUI:
            return MetadataWriter._serialize_comfyui(metadata)
        elif metadata.generator == GeneratorType.NOVELAI:
            return MetadataWriter._serialize_novelai(metadata)
        elif metadata.generator == GeneratorType.FOOOCUS:
            return MetadataWriter._serialize_fooocus(metadata)
        else:
            # Unknown format: write as A1111-style parameters
            return MetadataWriter._serialize_a1111(metadata)

    @staticmethod
    def _serialize_a1111(metadata: ImageMetadata) -> dict[str, str]:
        """Serialize to A1111 parameters format."""
        parts = [metadata.positive_prompt]
        if metadata.negative_prompt:
            parts.append(f"Negative prompt: {metadata.negative_prompt}")

        # Build params line
        params = dict(metadata.parameters)
        if metadata.model_name and "Model" not in params:
            params["Model"] = metadata.model_name
        if metadata.model_hash and "Model hash" not in params:
            params["Model hash"] = metadata.model_hash

        if params:
            param_str = ", ".join(f"{k}: {v}" for k, v in params.items())
            parts.append(param_str)

        return {"parameters": "\n".join(parts)}

    @staticmethod
    def _serialize_comfyui(metadata: ImageMetadata) -> dict[str, str]:
        """Serialize ComfyUI metadata. Preserves original workflow if available."""
        chunks: dict[str, str] = {}
        if metadata.workflow_json:
            chunks["workflow"] = metadata.workflow_json
        # For prompt chunk, we'd need the full node graph which we don't reconstruct
        # Use raw_chunks as fallback
        if "prompt" in metadata.raw_chunks:
            chunks["prompt"] = metadata.raw_chunks["prompt"]
        return chunks

    @staticmethod
    def _serialize_novelai(metadata: ImageMetadata) -> dict[str, str]:
        """Serialize to NovelAI format."""
        import json

        chunks: dict[str, str] = {}
        if metadata.positive_prompt:
            chunks["Description"] = metadata.positive_prompt

        comment: dict = {}
        if metadata.negative_prompt:
            comment["uc"] = metadata.negative_prompt
        for key, val in metadata.parameters.items():
            actual_key = "scale" if key == "cfg_scale" else key
            comment[actual_key] = val
        if comment:
            chunks["Comment"] = json.dumps(comment)
        chunks["Software"] = "NovelAI"

        return chunks

    @staticmethod
    def _serialize_fooocus(metadata: ImageMetadata) -> dict[str, str]:
        """Serialize to Fooocus JSON format."""
        import json

        data: dict = {
            "prompt": metadata.positive_prompt,
            "negative_prompt": metadata.negative_prompt,
        }
        data.update(metadata.parameters)
        if metadata.model_name:
            data["base_model"] = metadata.model_name
        if metadata.loras:
            data["loras"] = metadata.loras

        return {"parameters": json.dumps(data)}
