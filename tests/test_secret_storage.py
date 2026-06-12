"""API key 凭据存储：落盘剥离、读取回填、明文降级、迁移、清除（0.10.5）。"""
import json

import pytest

from native_app import secret_store
from native_app.models import AppState
from native_app.storage._paths import StoragePaths
from native_app.storage._state import StateStorage


@pytest.fixture
def fake_store(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(secret_store, "available", lambda: True)
    monkeypatch.setattr(
        secret_store, "get_secret",
        lambda name, service=secret_store._SERVICE: store.get(name),
    )

    def _set(name, value, service=secret_store._SERVICE):
        store[name] = value
        return True

    def _delete(name, service=secret_store._SERVICE):
        return store.pop(name, None) is not None

    monkeypatch.setattr(secret_store, "set_secret", _set)
    monkeypatch.setattr(secret_store, "delete_secret", _delete)
    return store


@pytest.fixture
def broken_store(monkeypatch):
    monkeypatch.setattr(secret_store, "available", lambda: False)
    monkeypatch.setattr(
        secret_store, "get_secret", lambda name, service=secret_store._SERVICE: None
    )
    monkeypatch.setattr(
        secret_store, "set_secret", lambda name, value, service=secret_store._SERVICE: False
    )
    monkeypatch.setattr(
        secret_store, "delete_secret", lambda name, service=secret_store._SERVICE: False
    )


def _storage(tmp_path) -> StateStorage:
    return StateStorage(StoragePaths.from_app_dir(tmp_path / "appdata"))


def _state_with_keys(api_key="", tagger_key="") -> AppState:
    return AppState.from_dict({
        "settings": {"api_key": api_key, "tagger_llm_api_key": tagger_key},
    })


def _disk_settings(storage: StateStorage) -> dict:
    return json.loads(storage._paths.settings_path.read_text(encoding="utf-8"))["settings"]


class TestSaveStripsSecrets:
    def test_keys_moved_to_store_and_blanked_on_disk(self, tmp_path, fake_store):
        storage = _storage(tmp_path)
        storage.save_state(_state_with_keys("sk-main", "sk-tagger"))
        disk = _disk_settings(storage)
        assert disk["api_key"] == ""
        assert disk["tagger_llm_api_key"] == ""
        assert fake_store == {"api_key": "sk-main", "tagger_llm_api_key": "sk-tagger"}

    def test_store_failure_keeps_plaintext(self, tmp_path, broken_store):
        storage = _storage(tmp_path)
        storage.save_state(_state_with_keys("sk-main"))
        assert _disk_settings(storage)["api_key"] == "sk-main"

    def test_cleared_key_deleted_from_store(self, tmp_path, fake_store):
        fake_store["api_key"] = "sk-old"
        storage = _storage(tmp_path)
        storage.save_state(_state_with_keys(api_key=""))
        assert "api_key" not in fake_store

    def test_in_memory_state_not_mutated(self, tmp_path, fake_store):
        state = _state_with_keys("sk-main")
        _storage(tmp_path).save_state(state)
        assert state.settings.api_key == "sk-main"


class TestLoadRestoresSecrets:
    def test_blank_disk_filled_from_store(self, tmp_path, fake_store):
        storage = _storage(tmp_path)
        storage.save_state(_state_with_keys("sk-main", "sk-tagger"))
        loaded = storage.load_state()
        assert loaded.settings.api_key == "sk-main"
        assert loaded.settings.tagger_llm_api_key == "sk-tagger"

    def test_legacy_plaintext_wins_over_store(self, tmp_path, fake_store):
        fake_store["api_key"] = "sk-from-store"
        storage = _storage(tmp_path)
        storage._paths.settings_path.parent.mkdir(parents=True, exist_ok=True)
        storage._paths.settings_path.write_text(
            json.dumps({"settings": {"api_key": "sk-legacy"}}), encoding="utf-8"
        )
        assert storage.load_state().settings.api_key == "sk-legacy"

    def test_legacy_plaintext_migrates_on_next_save(self, tmp_path, fake_store):
        storage = _storage(tmp_path)
        storage._paths.settings_path.parent.mkdir(parents=True, exist_ok=True)
        storage._paths.settings_path.write_text(
            json.dumps({"settings": {"api_key": "sk-legacy"}}), encoding="utf-8"
        )
        storage.save_state(storage.load_state())
        assert fake_store["api_key"] == "sk-legacy"
        assert _disk_settings(storage)["api_key"] == ""

    def test_store_unavailable_plaintext_roundtrip(self, tmp_path, broken_store):
        storage = _storage(tmp_path)
        storage.save_state(_state_with_keys("sk-main"))
        assert storage.load_state().settings.api_key == "sk-main"

    def test_missing_file_returns_default(self, tmp_path, fake_store):
        assert _storage(tmp_path).load_state().settings.api_key == ""
