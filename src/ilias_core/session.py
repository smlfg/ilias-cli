"""Token-Speicher pro Instanz (A4).

Bevorzugt der OS-Schlüsselbund über ``keyring``. Ist kein Keyring nutzbar,
Fallback auf eine Datei, die mit ``os.open(..., 0o600)`` **von Anfang an** mit
Rechten 0600 angelegt wird. Der Token wird nie geloggt oder ausgegeben.
"""

from __future__ import annotations

import os
from pathlib import Path

SERVICE_NAME = "ilias-cli"


class TokenStore:
    def __init__(self, config_dir: Path, lms: str, instance: str) -> None:
        self._config_dir = Path(config_dir)
        self._lms = lms
        safe_instance = _safe(instance)
        self._username = f"{lms}:{instance}"
        self._file = self._config_dir / "tokens" / f"{_safe(lms)}-{safe_instance}.token"

    # -- öffentliche API -------------------------------------------------
    def load(self) -> str | None:
        value = self._keyring_get()
        if value:
            return value
        if self._file.exists():
            try:
                token = self._file.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            return token or None
        return None

    def save(self, token: str) -> None:
        if self._keyring_set(token):
            self._remove_file()
            return
        self._write_file(token)

    def delete(self) -> bool:
        had_token = self.load() is not None
        self._keyring_delete()
        had_file = self._file.exists()
        self._remove_file()
        return had_token or had_file

    @property
    def file_path(self) -> Path:
        return self._file

    # -- Keyring ---------------------------------------------------------
    def _keyring_get(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(SERVICE_NAME, self._username)
        except Exception:
            return None

    def _keyring_set(self, token: str) -> bool:
        try:
            import keyring

            keyring.set_password(SERVICE_NAME, self._username, token)
            return True
        except Exception:
            return False

    def _keyring_delete(self) -> None:
        try:
            import keyring

            keyring.delete_password(SERVICE_NAME, self._username)
        except Exception:
            pass

    # -- Datei-Fallback --------------------------------------------------
    def _write_file(self, token: str) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, (token + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        try:
            os.chmod(self._file, 0o600)
        except OSError:
            pass

    def _remove_file(self) -> None:
        try:
            self._file.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _safe(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "default"
