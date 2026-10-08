"""Token-Ablage: OS-Keyring bevorzugt, sonst 0600-Datei. Pro Instanz."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import config as config_mod


def _safe_instance(instance: str | None) -> str:
    key = config_mod.instance_key(instance)
    return re.sub(r"[^A-Za-z0-9_-]", "_", key)


def token_file_path(instance: str | None) -> Path:
    return config_mod.config_dir() / f"moodle_token_{_safe_instance(instance)}.json"


SERVICE = "ilias-cli"


def _account(instance: str | None) -> str:
    return f"moodle:{_safe_instance(instance)}"


def _keyring_usable() -> bool:
    try:
        import keyring
        import keyring.errors

        # fail-Backend erkennen: get_password wirft oder Backend ist fail.
        try:
            backend = keyring.get_keyring()
            name = type(backend).__module__ + "." + type(backend).__name__
            if "fail" in name.lower():
                return False
        except Exception:
            return False
        return True
    except Exception:
        return False


def save_token(instance: str | None, token: str) -> str:
    """Speichert Token, gibt Ablage zurück ('keyring'|'file'). Wirft nie mit Token im Text."""
    if _keyring_usable():
        try:
            import keyring

            keyring.set_password(SERVICE, _account(instance), token)
            return "keyring"
        except Exception:
            pass
    path = token_file_path(instance)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"token": token})
    data = payload.encode("utf-8")
    # 0600 von Anfang an: os.open mit mode 0o600.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        pass
    return "file"


def load_token(instance: str | None) -> str | None:
    if _keyring_usable():
        try:
            import keyring

            value = keyring.get_password(SERVICE, _account(instance))
            if value:
                return value
        except Exception:
            pass
    path = token_file_path(instance)
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    token = obj.get("token") if isinstance(obj, dict) else None
    if isinstance(token, str) and token:
        return token
    return None


def delete_token(instance: str | None) -> None:
    if _keyring_usable():
        try:
            import keyring

            try:
                keyring.delete_password(SERVICE, _account(instance))
            except Exception:
                pass
        except Exception:
            pass
    # Datei immer entfernen (auch wenn Keyring genutzt wurde).
    try:
        token_file_path(instance).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass
