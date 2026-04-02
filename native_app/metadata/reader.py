from __future__ import annotations

import os

from .models import ImageMetadata
from .parsers.base import BaseMetadataParser
from .parsers.novelai import NovelAIParser
from .parsers.a1111 import A1111Parser
from .parsers.comfyui import ComfyUIParser
from .parsers.fooocus import FooocusParser


class MetadataReader:
    """Reads and parses metadata from AI-generated images.

    Supports PNG (tEXt/iTXt chunks), JPEG/WebP (EXIF UserComment).
    Parser priority: NovelAI → Fooocus → ComfyUI → A1111 (most specific first).
    """

    def __init__(self) -> None:
        self._parsers: list[BaseMetadataParser] = [
            NovelAIParser(),
            FooocusParser(),
            ComfyUIParser(),
            A1111Parser(),
        ]

    def read_metadata(self, path: str) -> ImageMetadata | None:
        """Read and parse metadata from an image file.

        Returns ``None`` if the file cannot be read or no parser matches.
        """
        if not os.path.isfile(path):
            return None

        ext = os.path.splitext(path)[1].lower()
        if ext == ".png":
            chunks = self._read_png_text_chunks(path)
        elif ext in (".jpg", ".jpeg", ".webp"):
            chunks = self._read_exif_comment(path)
        else:
            return None

        if not chunks:
            # For PNG, still try stealth (NovelAI might have no text chunks)
            if ext == ".png":
                parser = NovelAIParser()
                result = parser.parse({}, image_path=path)
                return result if result.has_content else None
            return None

        for parser in self._parsers:
            if parser.can_parse(chunks):
                return parser.parse(chunks, image_path=path)
        return None

    @staticmethod
    def _read_png_text_chunks(path: str) -> dict[str, str]:
        """Read PNG tEXt/iTXt/zTXt chunks directly from binary.

        PIL has a known bug where iTXt chunks are decoded as latin-1
        instead of UTF-8, so we parse chunks ourselves.
        """
        import struct
        import zlib

        _PNG_SIG = b"\x89PNG\r\n\x1a\n"
        chunks: dict[str, str] = {}

        try:
            with open(path, "rb") as f:
                sig = f.read(8)
                if sig != _PNG_SIG:
                    return {}

                while True:
                    length_bytes = f.read(4)
                    if len(length_bytes) < 4:
                        break
                    length = struct.unpack(">I", length_bytes)[0]
                    chunk_type = f.read(4)
                    chunk_data = f.read(length)
                    f.read(4)  # CRC

                    if chunk_type == b"tEXt":
                        # keyword\0text — spec says latin-1, but many tools
                        # (including A1111 WebUI) write UTF-8. Try UTF-8 first.
                        null_idx = chunk_data.find(b"\x00")
                        if null_idx != -1:
                            keyword = chunk_data[:null_idx].decode("latin-1", errors="replace")
                            text_bytes = chunk_data[null_idx + 1:]
                            try:
                                text = text_bytes.decode("utf-8")
                            except UnicodeDecodeError:
                                text = text_bytes.decode("latin-1", errors="replace")
                            chunks[keyword] = text

                    elif chunk_type == b"iTXt":
                        # keyword\0 compression_flag compression_method language\0 translated\0 text
                        null_idx = chunk_data.find(b"\x00")
                        if null_idx != -1:
                            keyword = chunk_data[:null_idx].decode("latin-1", errors="replace")
                            rest = chunk_data[null_idx + 1:]
                            if len(rest) >= 2:
                                comp_flag = rest[0]
                                comp_method = rest[1]
                                rest = rest[2:]
                                # Skip language tag
                                lang_end = rest.find(b"\x00")
                                if lang_end != -1:
                                    rest = rest[lang_end + 1:]
                                    # Skip translated keyword
                                    trans_end = rest.find(b"\x00")
                                    if trans_end != -1:
                                        text_bytes = rest[trans_end + 1:]
                                        if comp_flag == 1:
                                            try:
                                                text_bytes = zlib.decompress(text_bytes)
                                            except zlib.error:
                                                pass
                                        chunks[keyword] = text_bytes.decode("utf-8", errors="replace")

                    elif chunk_type == b"zTXt":
                        # keyword\0 compression_method compressed_text
                        null_idx = chunk_data.find(b"\x00")
                        if null_idx != -1:
                            keyword = chunk_data[:null_idx].decode("latin-1", errors="replace")
                            comp_data = chunk_data[null_idx + 2:]  # skip null + compression method byte
                            try:
                                text = zlib.decompress(comp_data).decode("latin-1", errors="replace")
                            except zlib.error:
                                text = ""
                            chunks[keyword] = text

                    elif chunk_type == b"IEND":
                        break

        except Exception:
            return {}

        return chunks

    @staticmethod
    def _read_exif_comment(path: str) -> dict[str, str]:
        """Read EXIF UserComment from JPEG/WebP (A1111 format)."""
        try:
            from PIL import Image
            from PIL.ExifTags import Base as ExifBase

            img = Image.open(path)
            exif = img.getexif()
            img.close()

            # UserComment tag ID = 0x9286
            user_comment = exif.get(0x9286, "")
            if isinstance(user_comment, bytes):
                # Strip encoding prefix (8 bytes: "ASCII\x00\x00\x00" or "UNICODE\x00")
                if user_comment.startswith(b"ASCII\x00\x00\x00"):
                    user_comment = user_comment[8:].decode("ascii", errors="replace")
                elif user_comment.startswith(b"UNICODE\x00"):
                    user_comment = user_comment[8:].decode("utf-16", errors="replace")
                else:
                    user_comment = user_comment.decode("utf-8", errors="replace")
                user_comment = user_comment.replace("\x00", "")

            if user_comment:
                return {"parameters": user_comment}
            return {}
        except Exception:
            return {}
