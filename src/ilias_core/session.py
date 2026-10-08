"""Session storage: OS keyring with 0600 file fallback. Never logs cookies."""

from __future__ import annotations

import json
import logging
import os

from ilias_core import config as config_mod

log = logging.getLogger(__name__)

SERVICE_NAME = "ilias-cli"
ACCOUNT_NAME = "session-cookies"
SESSION_FILENAME = "session.json"


def _config_dir(config_dir: str | None = None) -> str:
    return config_dir or config_mod.default_config_dir()


def session_file_path(config_dir: str | None = None) -> str:
    return os.path.join(_config_dir(config_dir), SESSION_FILENAME)


# --- keyring backend (injectable for tests) ---

_keyring_backend = None  # None = auto (real keyring); otherwise object with get/set/delete


def set_keyring_backend(backend) -> None:
    """Inject an in-memory/fake keyring for tests. Pass None to restore auto."""
    global _keyring_backend
    _keyring_backend = backend


def _keyring_get() -> str | None:
    if _keyring_backend is not None:
        return _keyring_backend.get_password(SERVICE_NAME, ACCOUNT_NAME)
    try:
        import keyring

        return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except Exception as exc:  # no backend available etc.
        log.debug("keyring unavailable, using file fallback: %s", type(exc).__name__)
        return None


def _keyring_set(payload: str) -> bool:
    if _keyring_backend is not None:
        _keyring_backend.set_password(SERVICE_NAME, ACCOUNT_NAME, payload)
        return True
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, payload)
        return True
    except Exception as exc:
        log.debug("keyring store failed, using file fallback: %s", type(exc).__name__)
        return False


def _keyring_delete() -> bool:
    if _keyring_backend is not None:
        try:
            _keyring_backend.delete_password(SERVICE_NAME, ACCOUNT_NAME)
        except Exception:
            pass
        return True
    try:
        import keyring

        try:
            keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _keyring_usable() -> bool:
    if _keyring_backend is not None:
        return True
    try:
        import keyring

        backend = keyring.get_keyring()
        # keyring's fail backend means "no usable backend"
        name = type(backend).__name__.lower()
        module = type(backend).__module__.lower()
        if "fail" in name or "fail" in module:
            return False
        return True
    except Exception:
        return False


# --- file fallback ---


def _write_session_file(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Write with 0600: create with O_CREAT|O_WRONLY|O_TRUNC and mode 0o600
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except BaseException:
        # os.fdopen closed fd on success; on error ensure close
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_session_file(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None
    return data


# --- public API (cookies as plain dict, never logged) ---


def save_session(
    cookies: dict[str, str],
    username: str | None = None,
    base_url: str | None = None,
    config_dir: str | None = None,
) -> str:
    """Persist session cookies. Returns 'keyring' or 'file'. Never logs values."""
    payload = {
        "cookies": dict(cookies or {}),
        "username": username,
        "base_url": base_url,
    }
    raw = json.dumps(payload)
    if _keyring_usable() and _keyring_set(raw):
        # Remove stale file fallback so only one store holds the session.
        try:
            fp = session_file_path(config_dir)
            if os.path.exists(fp):
                os.remove(fp)
        except OSError:
            pass
        return "keyring"
    fp = session_file_path(config_dir)
    _write_session_file(fp, payload)
    return "file"


def load_session(config_dir: str | None = None) -> dict | None:
    """Return stored payload {'cookies', 'username', 'base_url'} or None."""
    raw = _keyring_get()
    if raw:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("cookies"), dict):
            return data
    # Fallback / primary when no keyring: file
    try:
        data = _read_session_file(session_file_path(config_dir))
    except (ValueError, OSError):
        return None
    if isinstance(data, dict) and isinstance(data.get("cookies"), dict) and data["cookies"]:
        return data
    return None


def clear_session(config_dir: str | None = None) -> None:
    _keyring_delete()
    fp = session_file_path(config_dir)
    try:
        if os.path.exists(fp):
            os.remove(fp)
    except OSError:
        pass


def has_session(config_dir: str | None = None) -> bool:
    return load_session(config_dir) is not None
