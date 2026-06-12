"""消息组装（depth 插入语义）、输入提取、URL 归一、token 估算。"""
from native_app.logic import (
    build_messages,
    estimate_messages_tokens,
    estimate_text_tokens,
    extract_active_input,
    normalize_api_base_url,
    validate_examples,
)
from native_app.models import ExampleEntry, OCEntry, OutfitEntry, PromptEntry


class TestNormalizeApiBaseUrl:
    def test_strips_trailing_slash(self):
        assert normalize_api_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"

    def test_strips_chat_completions_suffix(self):
        assert normalize_api_base_url("https://api.example.com/v1/chat/completions") == "https://api.example.com/v1"

    def test_strips_suffix_with_trailing_slash(self):
        assert normalize_api_base_url("https://api.example.com/v1/chat/completions/") == "https://api.example.com/v1"

    def test_strips_whitespace(self):
        assert normalize_api_base_url("  https://api.example.com/v1  ") == "https://api.example.com/v1"


class TestExtractActiveInput:
    def test_memory_mode_returns_everything(self):
        assert extract_active_input("old --- new", memory_mode=True) == "old --- new"

    def test_normal_mode_takes_last_section(self):
        assert extract_active_input("old --- new", memory_mode=False) == "new"

    def test_no_separator(self):
        assert extract_active_input("only text", memory_mode=False) == "only text"

    def test_trailing_separator_yields_empty(self):
        assert extract_active_input("old ---", memory_mode=False) == ""


class TestValidateExamples:
    def test_desc_without_tags_is_error(self):
        assert len(validate_examples([ExampleEntry(description="d", tags="")])) == 1

    def test_both_present_ok(self):
        assert validate_examples([ExampleEntry(description="d", tags="t")]) == []

    def test_both_empty_ok(self):
        assert validate_examples([ExampleEntry()]) == []


class TestBuildMessages:
    def test_depth_zero_lands_after_input(self):
        prompt = PromptEntry(role="system", content="sys", depth=0, order=1)
        messages = build_messages([prompt], [], "hi", memory_mode=False)
        assert [m["role"] for m in messages] == ["user", "system"]
        assert messages[0]["content"] == "hi"

    def test_deep_entry_lands_above_input(self):
        prompt = PromptEntry(role="system", content="sys", depth=4, order=1)
        messages = build_messages([prompt], [], "hi", memory_mode=False)
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_same_depth_ordered_by_order(self):
        p1 = PromptEntry(role="system", content="first", depth=4, order=1)
        p2 = PromptEntry(role="system", content="second", depth=4, order=2)
        messages = build_messages([p2, p1], [], "hi", memory_mode=False)
        assert [m["content"] for m in messages[:2]] == ["first", "second"]

    def test_disabled_prompt_excluded(self):
        prompt = PromptEntry(content="sys", enabled=False)
        assert build_messages([prompt], [], "hi", memory_mode=False) == [
            {"role": "user", "content": "hi"},
        ]

    def test_incomplete_example_excluded(self):
        example = ExampleEntry(description="d", tags="")
        assert build_messages([], [example], "hi", memory_mode=False) == [
            {"role": "user", "content": "hi"},
        ]

    def test_example_becomes_assistant_message(self):
        example = ExampleEntry(description="a girl", tags="1girl, solo", depth=4)
        messages = build_messages([], [example], "hi", memory_mode=False)
        assert messages[0]["role"] == "assistant"
        assert "1girl, solo" in messages[0]["content"]
        assert "a girl" in messages[0]["content"]

    def test_example_lora_tokens_stripped(self):
        example = ExampleEntry(description="d", tags="<lora:style:0.8>, 1girl", depth=4)
        messages = build_messages([], [example], "hi", memory_mode=False)
        assert "<lora:" not in messages[0]["content"]
        assert "1girl" in messages[0]["content"]

    def test_oc_entry_emits_user_assistant_pair(self):
        oc = OCEntry(character_name="Hein", tags="blonde hair", depth=4,
                     outfits=[OutfitEntry(name="red", tags="red dress", active=True)])
        messages = build_messages([], [], "hi", memory_mode=False, ocs=[oc])
        assert messages[0] == {"role": "user", "content": "Character: Hein"}
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "blonde hair, red dress"

    def test_history_prepended_in_memory_mode(self):
        history = [
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "reply"},
            {"role": "tool", "content": "dropped"},
            {"role": "user", "content": ""},
        ]
        messages = build_messages([], [], "hi", memory_mode=True, history=history)
        assert messages == [
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "hi"},
        ]

    def test_deep_entry_stays_above_history(self):
        prompt = PromptEntry(role="system", content="sys", depth=99, order=1)
        history = [{"role": "user", "content": "earlier"}]
        messages = build_messages([prompt], [], "hi", memory_mode=True, history=history)
        assert messages[0]["content"] == "sys"
        assert messages[1]["content"] == "earlier"


class TestTokenEstimates:
    def test_empty_is_zero(self):
        assert estimate_text_tokens("") == 0
        assert estimate_text_tokens("   ") == 0

    def test_english_word(self):
        assert estimate_text_tokens("hello") == 2  # ceil(1.3)

    def test_cjk_counts_double(self):
        assert estimate_text_tokens("你好") == 4

    def test_messages_overhead(self):
        assert estimate_messages_tokens([]) == 0
        assert estimate_messages_tokens([{"role": "user", "content": "hello"}]) == 8  # 4 + 2 + 2
