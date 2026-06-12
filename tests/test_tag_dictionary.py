"""Danbooru CSV 词典：解析、别名索引、大小写归一、CJK 子串搜索。"""
import csv

from native_app.tag_dictionary import TagDictionary

ROWS = [
    ["long_hair", "0", "1000", "longhair,long hair", "长发", "外观", "头发"],
    ["long_dress", "0", "50", "", "长裙", "外观", "服装"],
    ["1girl", "0", "5000", "", "1个女孩", "人物", ""],
    ["blue_eyes", "0", "800", "blueeyes", "蓝眼睛", "外观", "眼睛"],
    ["malformed"],
]


def _write_csv(tmp_path):
    path = tmp_path / "tags.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(ROWS)
    return path


def _dictionary(tmp_path):
    d = TagDictionary()
    d.load_csv(_write_csv(tmp_path))
    return d


class TestParsing:
    def test_malformed_rows_skipped(self, tmp_path):
        assert len(_dictionary(tmp_path)) == 4

    def test_missing_file_is_noop(self, tmp_path):
        d = TagDictionary()
        d.load_csv(tmp_path / "missing.csv")
        assert len(d) == 0

    def test_queue_csv_loads_lazily_on_lookup(self, tmp_path):
        d = TagDictionary()
        d.queue_csv(_write_csv(tmp_path))
        assert d.lookup("1girl") is not None


class TestLookup:
    def test_exact(self, tmp_path):
        info = _dictionary(tmp_path).lookup("long_hair")
        assert info.translation == "长发"
        assert info.category_id == 0
        assert info.count == 1000

    def test_case_and_space_insensitive(self, tmp_path):
        assert _dictionary(tmp_path).lookup("Long Hair").name == "long_hair"

    def test_alias_resolves_to_canonical(self, tmp_path):
        assert _dictionary(tmp_path).lookup("longhair").name == "long_hair"
        assert _dictionary(tmp_path).lookup("blueeyes").name == "blue_eyes"

    def test_translate(self, tmp_path):
        d = _dictionary(tmp_path)
        assert d.translate("1girl") == "1个女孩"
        assert d.translate("unknown_tag") is None

    def test_contains(self, tmp_path):
        d = _dictionary(tmp_path)
        assert "1girl" in d
        assert "unknown_tag" not in d


class TestSearchPrefix:
    def test_ascii_prefix_ranked_by_count(self, tmp_path):
        names = [t.name for t in _dictionary(tmp_path).search_prefix("long")]
        assert names == ["long_hair", "long_dress"]

    def test_alias_prefix_matches(self, tmp_path):
        names = [t.name for t in _dictionary(tmp_path).search_prefix("blueey")]
        assert names == ["blue_eyes"]

    def test_limit_respected(self, tmp_path):
        assert len(_dictionary(tmp_path).search_prefix("long", limit=1)) == 1

    def test_cjk_substring_matches_translation(self, tmp_path):
        names = [t.name for t in _dictionary(tmp_path).search_prefix("女孩")]
        assert names == ["1girl"]

    def test_cjk_middle_character(self, tmp_path):
        names = [t.name for t in _dictionary(tmp_path).search_prefix("眼")]
        assert names == ["blue_eyes"]

    def test_empty_query(self, tmp_path):
        assert _dictionary(tmp_path).search_prefix("") == []
        assert _dictionary(tmp_path).search_prefix("   ") == []
