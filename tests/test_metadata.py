"""PNG 文本 chunk 写读往返与截断防护（0.10.0 截断 chunk 修复回归）。"""
import struct
import zlib

import pytest

from native_app.metadata.reader import MetadataReader
from native_app.metadata.writer import MetadataWriter


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def make_minimal_png(path) -> None:
    """1x1 RGBA PNG，无文本 chunk。"""
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00\xff")
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


class TestWriteReadRoundtrip:
    def test_ascii_text_roundtrip(self, tmp_path):
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        make_minimal_png(src)
        params = "1girl, solo\nNegative prompt: lowres\nSteps: 20"
        MetadataWriter().write_chunks(str(src), str(dst), {"parameters": params})
        assert MetadataReader._read_png_text_chunks(str(dst))["parameters"] == params

    def test_cjk_text_roundtrip_via_itxt(self, tmp_path):
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        make_minimal_png(src)
        text = "1girl, 黑发, 金色双马尾"
        MetadataWriter().write_chunks(str(src), str(dst), {"Description": text})
        assert MetadataReader._read_png_text_chunks(str(dst))["Description"] == text

    def test_idat_preserved_verbatim(self, tmp_path):
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        make_minimal_png(src)
        MetadataWriter().write_chunks(str(src), str(dst), {"parameters": "x"})
        src_idat = [d for t, d in MetadataWriter._read_raw_chunks(str(src)) if t == b"IDAT"]
        dst_idat = [d for t, d in MetadataWriter._read_raw_chunks(str(dst)) if t == b"IDAT"]
        assert src_idat == dst_idat

    def test_existing_text_chunks_replaced(self, tmp_path):
        src = tmp_path / "src.png"
        mid = tmp_path / "mid.png"
        dst = tmp_path / "dst.png"
        make_minimal_png(src)
        writer = MetadataWriter()
        writer.write_chunks(str(src), str(mid), {"parameters": "old secret"})
        writer.write_chunks(str(mid), str(dst), {"parameters": "new"})
        chunks = MetadataReader._read_png_text_chunks(str(dst))
        assert chunks["parameters"] == "new"
        assert "old secret" not in str(chunks)


class TestTruncatedFileGuard:
    def _truncated_png(self, tmp_path):
        src = tmp_path / "src.png"
        full = tmp_path / "full.png"
        make_minimal_png(src)
        MetadataWriter().write_chunks(str(src), str(full), {"parameters": "kept"})
        truncated = tmp_path / "truncated.png"
        # 砍掉 IEND(12 字节) 再深入 IDAT 尾部 8 字节 → IDAT 数据不完整
        truncated.write_bytes(full.read_bytes()[:-20])
        return truncated

    def test_reader_drops_partial_chunk_without_raising(self, tmp_path):
        truncated = self._truncated_png(tmp_path)
        chunks = MetadataReader._read_png_text_chunks(str(truncated))
        assert chunks["parameters"] == "kept"

    def test_writer_raw_read_drops_partial_chunk(self, tmp_path):
        truncated = self._truncated_png(tmp_path)
        types = [t for t, _ in MetadataWriter._read_raw_chunks(str(truncated))]
        assert b"IDAT" not in types  # 残缺 IDAT 被丢弃，不会写回输出
        assert b"IHDR" in types


class TestDestroy:
    def test_original_text_replaced_with_garbage(self, tmp_path):
        src = tmp_path / "src.png"
        mid = tmp_path / "mid.png"
        dst = tmp_path / "dst.png"
        make_minimal_png(src)
        writer = MetadataWriter()
        writer.write_chunks(str(src), str(mid), {"parameters": "real prompt"})
        writer.destroy(str(mid), str(dst), text="garbage")
        params = MetadataReader._read_png_text_chunks(str(dst))["parameters"]
        assert "real prompt" not in params
        assert "garbage" in params
        assert "Steps: 0" in params


class TestNonPng:
    def test_reader_returns_empty(self, tmp_path):
        bad = tmp_path / "not.png"
        bad.write_bytes(b"JFIF whatever")
        assert MetadataReader._read_png_text_chunks(str(bad)) == {}

    def test_writer_raises_value_error(self, tmp_path):
        bad = tmp_path / "not.png"
        bad.write_bytes(b"JFIF whatever")
        with pytest.raises(ValueError):
            MetadataWriter._read_raw_chunks(str(bad))
