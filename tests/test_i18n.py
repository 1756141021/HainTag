"""i18n 键集一致性（堵 0.10.0 英文界面混中文那次的洞）与 Translator 回退链。"""
import json
from pathlib import Path

from native_app.i18n import Translator

RESOURCES_DIR = Path(__file__).resolve().parents[1] / "native_app" / "resources"


class TestCatalogParity:
    def test_zh_and_en_have_identical_key_sets(self):
        lang_dir = RESOURCES_DIR / "lang"
        zh = json.loads((lang_dir / "zh-CN.json").read_text(encoding="utf-8"))
        en = json.loads((lang_dir / "en.json").read_text(encoding="utf-8"))
        only_zh = sorted(set(zh) - set(en))
        only_en = sorted(set(en) - set(zh))
        assert not only_zh and not only_en, (
            f"missing in en.json: {only_zh}; missing in zh-CN.json: {only_en}"
        )

    def test_no_empty_values(self):
        lang_dir = RESOURCES_DIR / "lang"
        for name in ("zh-CN.json", "en.json"):
            catalog = json.loads((lang_dir / name).read_text(encoding="utf-8"))
            empty = [k for k, v in catalog.items() if not str(v).strip()]
            assert not empty, f"{name} has empty values: {empty}"


def _make_resources(tmp_path):
    lang_dir = tmp_path / "lang"
    lang_dir.mkdir()
    (lang_dir / "zh-CN.json").write_text(
        json.dumps({"a": "甲"}, ensure_ascii=False), encoding="utf-8"
    )
    (lang_dir / "en.json").write_text(
        json.dumps({"a": "A", "b": "B"}), encoding="utf-8"
    )
    return tmp_path


class TestTranslator:
    def test_active_language_wins(self, tmp_path):
        t = Translator(_make_resources(tmp_path))
        assert t.t("a") == "甲"

    def test_missing_key_falls_back_to_en(self, tmp_path):
        t = Translator(_make_resources(tmp_path))
        assert t.t("b") == "B"

    def test_unknown_key_returns_key(self, tmp_path):
        t = Translator(_make_resources(tmp_path))
        assert t.t("nope") == "nope"

    def test_set_unknown_language_is_noop(self, tmp_path):
        t = Translator(_make_resources(tmp_path))
        t.set_language("xx-XX")
        assert t.get_language() == "zh-CN"

    def test_missing_default_language_falls_back_to_en(self, tmp_path):
        lang_dir = tmp_path / "lang"
        lang_dir.mkdir()
        (lang_dir / "en.json").write_text(json.dumps({"a": "A"}), encoding="utf-8")
        t = Translator(tmp_path)
        assert t.get_language() == "en"

    def test_real_catalogs_load(self):
        t = Translator(RESOURCES_DIR)
        assert {"zh-CN", "en"} <= set(t.available_languages())
        assert t.t("tutorial_open") != "tutorial_open"
