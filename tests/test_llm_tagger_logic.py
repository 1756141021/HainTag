"""回归重点：列表编号剥离不能吃掉 1girl/2girls 的前导数字（0.10.0 修复）。"""
import base64

from native_app.llm_tagger_logic import (
    _normalize_tag,
    build_vision_messages,
    parse_llm_tags,
    validate_tags,
)
from native_app.tag_dictionary import TagDictionary


class TestNormalizeTag:
    def test_count_tags_keep_leading_digits(self):
        assert _normalize_tag("1girl") == "1girl"
        assert _normalize_tag("2girls") == "2girls"
        assert _normalize_tag("1boy") == "1boy"

    def test_list_numbering_stripped(self):
        assert _normalize_tag("1. long_hair") == "long_hair"
        assert _normalize_tag("2) blue_eyes") == "blue_eyes"
        assert _normalize_tag("3] smile") == "smile"

    def test_bullets_stripped(self):
        assert _normalize_tag("- solo") == "solo"
        assert _normalize_tag("* solo") == "solo"

    def test_lowercase_and_underscore(self):
        assert _normalize_tag("Blue Eyes") == "blue_eyes"
        assert _normalize_tag("  white dress  ") == "white_dress"

    def test_surrounding_underscores_stripped(self):
        assert _normalize_tag("_solo_") == "solo"


class TestParseLlmTags:
    def test_comma_separated(self):
        assert parse_llm_tags("1girl, long hair, blue eyes") == [
            "1girl", "long_hair", "blue_eyes",
        ]

    def test_markdown_fence_stripped(self):
        assert parse_llm_tags("```\n1girl, solo, smile\n```") == [
            "1girl", "solo", "smile",
        ]

    def test_newline_fallback_when_no_commas(self):
        assert parse_llm_tags("1girl\nlong_hair\nsmile\nblue_eyes") == [
            "1girl", "long_hair", "smile", "blue_eyes",
        ]

    def test_numbered_list_lines(self):
        assert parse_llm_tags("1. 1girl\n2. long_hair\n3. smile") == [
            "1girl", "long_hair", "smile",
        ]

    def test_deduplicates(self):
        assert parse_llm_tags("solo, Solo, solo") == ["solo"]

    def test_comment_lines_filtered(self):
        assert parse_llm_tags("# header\n1girl\nsolo\nsmile") == [
            "1girl", "solo", "smile",
        ]

    def test_empty_input(self):
        assert parse_llm_tags("") == []
        assert parse_llm_tags("   \n  ") == []


class TestValidateTags:
    def _dictionary(self, tmp_path):
        csv_path = tmp_path / "tags.csv"
        csv_path.write_text(
            "long_hair,0,100,,长发\n1girl,0,500,,1个女孩\n",
            encoding="utf-8",
        )
        d = TagDictionary()
        d.load_csv(csv_path)
        return d

    def test_known_tag_fills_info(self, tmp_path):
        result = validate_tags(["1girl"], self._dictionary(tmp_path))
        assert result[0].is_valid
        assert result[0].translation == "1个女孩"

    def test_unknown_tag_invalid(self, tmp_path):
        result = validate_tags(["nonexistent_tag_xyz"], self._dictionary(tmp_path))
        assert not result[0].is_valid

    def test_no_dictionary_all_invalid(self):
        result = validate_tags(["1girl"], None)
        assert not result[0].is_valid


class TestBuildVisionMessages:
    def test_png_data_url_and_prompt(self, tmp_path):
        img = tmp_path / "sample.png"
        img.write_bytes(b"fakepng")
        messages = build_vision_messages(str(img), "describe this")
        content = messages[0]["content"]
        url = content[0]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")
        assert base64.b64decode(url.split(",", 1)[1]) == b"fakepng"
        assert content[1]["text"] == "describe this"

    def test_jpg_mime(self, tmp_path):
        img = tmp_path / "sample.JPG"
        img.write_bytes(b"x")
        messages = build_vision_messages(str(img), "p")
        assert messages[0]["content"][0]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,"
        )

    def test_unknown_extension_defaults_to_png(self, tmp_path):
        img = tmp_path / "sample.bmp"
        img.write_bytes(b"x")
        messages = build_vision_messages(str(img), "p")
        assert messages[0]["content"][0]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
