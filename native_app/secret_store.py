"""系统凭据存储薄封装（Windows 凭据管理器 / macOS Keychain，经 keyring）。

storage 层用它把 API key 移出 settings.json 明文。所有操作吞异常：
keyring 缺失、后端为 fail.Keyring、平台调用出错时一律降级为不可用，
调用方保持明文行为。
"""
from __future__ import annotations

_SERVICE = "HainTag"

_keyring = None
_checked = False


def _backend():
    global _keyring, _checked
    if _checked:
        return _keyring
    _checked = True
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        if isinstance(keyring.get_keyring(), FailKeyring):
            _keyring = None
        else:
            _keyring = keyring
    except Exception:
        _keyring = None
    return _keyring


def available() -> bool:
    return _backend() is not None


def get_secret(name: str, service: str | None = None) -> str | None:
    backend = _backend()
    if backend is None:
        return None
    try:
        return backend.get_password(service or _SERVICE, name)
    except Exception:
        return None


def set_secret(name: str, value: str, service: str | None = None) -> bool:
    backend = _backend()
    if backend is None:
        return False
    try:
        backend.set_password(service or _SERVICE, name, value)
        return True
    except Exception:
        return False


def delete_secret(name: str, service: str | None = None) -> bool:
    backend = _backend()
    if backend is None:
        return False
    try:
        backend.delete_password(service or _SERVICE, name)
        return True
    except Exception:
        return False
