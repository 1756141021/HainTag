"""AppSettings 序列化往返、legacy 键迁移、clamp 边界、字体默认值（0.10.0 改 default）。"""
from native_app.models import (
    AppSettings,
    ExampleEntry,
    OCEntry,
    OutfitEntry,
    PromptEntry,
    _migrate_llm_presets,
    clamp_float,
    clamp_int,
)


class TestClamps:
    def test_clamp_to_bounds(self):
        assert clamp_float(5.0, 1.0, 0.0, 2.0) == 2.0
        assert clamp_float(-1.0, 1.0, 0.0, 2.0) == 0.0
        assert clamp_int(999, 100, 50, 300) == 300

    def test_fallback_on_garbage(self):
        assert clamp_float("abc", 1.0, 0.0, 2.0) == 1.0
        assert clamp_int(None, 100, 50, 300) == 100


class TestAppSettingsDefaults:
    def test_fresh_install_font_is_default_profile(self):
        assert AppSettings().font_profile == "default"

    def test_from_empty_dict_font_is_default(self):
        assert AppSettings.from_dict({}).font_profile == "default"

    def test_persisted_wenkai_preserved(self):
        assert AppSettings.from_dict({"font_profile": "wenkai"}).font_profile == "wenkai"

    def test_empty_font_profile_falls_back(self):
        assert AppSettings.from_dict({"font_profile": ""}).font_profile == "default"
        assert AppSettings.from_dict({"font_profile": None}).font_profile == "default"

    def test_core_defaults(self):
        s = AppSettings.from_dict({})
        assert s.theme == "dark"
        assert s.language == "zh-CN"
        assert s.memory_mode is True
        assert s.ui_scale_percent == 100


class TestAppSettingsRoundtrip:
    def test_default_roundtrip_equal(self):
        s = AppSettings()
        assert AppSettings.from_dict(s.to_dict()) == s

    def test_custom_values_roundtrip(self):
        s = AppSettings(api_base_url="https://x/v1", temperature=0.7, top_k=5,
                        font_profile="wenkai", card_opacity=55)
        restored = AppSettings.from_dict(s.to_dict())
        assert restored == s


class TestAppSettingsLegacyKeys:
    def test_camel_case_keys_migrated(self):
        s = AppSettings.from_dict({
            "apiUrl": "https://legacy/v1",
            "apiKey": "sk-old",
            "topP": 0.9,
            "maxTokens": 4096,
        })
        assert s.api_base_url == "https://legacy/v1"
        assert s.api_key == "sk-old"
        assert s.top_p == 0.9
        assert s.max_tokens == 4096

    def test_new_keys_win_over_legacy(self):
        s = AppSettings.from_dict({"api_base_url": "https://new/v1", "apiUrl": "https://old/v1"})
        assert s.api_base_url == "https://new/v1"


class TestAppSettingsTopK:
    def test_empty_and_none_mean_unset(self):
        assert AppSettings.from_dict({"top_k": ""}).top_k is None
        assert AppSettings.from_dict({"top_k": None}).top_k is None

    def test_numeric_string_parsed(self):
        assert AppSettings.from_dict({"top_k": "5"}).top_k == 5

    def test_negative_clamped_to_zero(self):
        assert AppSettings.from_dict({"top_k": -3}).top_k == 0

    def test_garbage_means_unset(self):
        assert AppSettings.from_dict({"top_k": "abc"}).top_k is None


class TestMigrateLlmPresets:
    def test_existing_list_passthrough(self):
        presets = [{"name": "A", "text": "t"}]
        assert _migrate_llm_presets({"tagger_llm_presets": presets}) == presets

    def test_old_custom_prompt_wrapped(self):
        result = _migrate_llm_presets({"tagger_llm_custom_prompt": "describe"})
        assert result == [{"name": "Custom", "text": "describe"}]

    def test_nothing_yields_empty(self):
        assert _migrate_llm_presets({}) == []


class TestEntrySerialization:
    def test_prompt_entry_roundtrip(self):
        p = PromptEntry(name="N", role="user", depth=2, order=7, enabled=False, content="c")
        assert PromptEntry.from_dict(p.to_dict()) == p

    def test_example_entry_legacy_desc_key(self):
        e = ExampleEntry.from_dict({"desc": "old description", "tags": "t"})
        assert e.description == "old description"

    def test_oc_entry_outfits_roundtrip(self):
        oc = OCEntry(character_name="Hein", tags="blonde",
                     outfits=[OutfitEntry(name="red", tags="dress", active=True)])
        restored = OCEntry.from_dict(oc.to_dict())
        assert restored == oc

    def test_merged_tags_only_active_outfits(self):
        oc = OCEntry(tags="blonde", outfits=[
            OutfitEntry(name="a", tags="red dress", active=True),
            OutfitEntry(name="b", tags="armor", active=False),
            OutfitEntry(name="c", tags="   ", active=True),
        ])
        assert oc.merged_tags() == "blonde, red dress"
