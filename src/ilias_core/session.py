"""Session/Token-Speicherung: Keyring (bevorzugt) + Datei-Fallback mit 0600 Rechten."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import keyring
from keyring.errors import NoKeyringError

from .config import get_config_dir
from .models import IliasSession, MoodleSiteInfo


# Keyring Service-Namen
MOODLE_TOKEN_SERVICE = "ilias-cli-moodle-token"
ILIAS_SESSION_SERVICE = "ilias-cli-ilias-session"


class SessionStore:
    """Einheitliche Session/Token-Speicherung pro Instanz."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = get_config_dir(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    # --- Moodle Token ---

    def _moodle_keyring_key(self, instance_name: str) -> str:
        return f"moodle-token:{instance_name}"

    def _moodle_file_path(self, instance_name: str) -> Path:
        safe_name = instance_name.replace("/", "_").replace(":", "_")
        return self.config_dir / f"moodle_token_{safe_name}.json"

    def save_moodle_token(
        self, instance_name: str, token: str, site_info: MoodleSiteInfo | None = None
    ) -> None:
        """Speichert Moodle Token + Site-Info (Keyring oder Datei 0600)."""
        data = {"token": token}
        if site_info:
            data["site_info"] = {
                "sitename": site_info.sitename,
                "username": site_info.username,
                "fullname": site_info.fullname,
                "userid": site_info.userid,
                "siteurl": site_info.siteurl,
            }

        # Erst Keyring versuchen
        try:
            keyring.set_password(MOODLE_TOKEN_SERVICE, self._moodle_keyring_key(instance_name), json.dumps(data))
            return
        except (NoKeyringError, Exception):
            pass

        # Fallback: Datei mit 0600
        file_path = self._moodle_file_path(instance_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # os.open mit 0o600 für sichere Erstellung
        fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            os.close(fd)
            raise

    def load_moodle_token(self, instance_name: str) -> tuple[str | None, MoodleSiteInfo | None]:
        """Lädt Moodle Token + Site-Info. Returns (token, site_info) or (None, None)."""
        # Erst Keyring versuchen
        try:
            stored = keyring.get_password(MOODLE_TOKEN_SERVICE, self._moodle_keyring_key(instance_name))
            if stored:
                data = json.loads(stored)
                token = data.get("token")
                site_info = None
                if si := data.get("site_info"):
                    site_info = MoodleSiteInfo(
                        sitename=si.get("sitename", ""),
                        username=si.get("username", ""),
                        fullname=si.get("fullname", ""),
                        userid=si.get("userid", 0),
                        siteurl=si.get("siteurl", ""),
                    )
                return token, site_info
        except (NoKeyringError, Exception):
            pass

        # Fallback: Datei
        file_path = self._moodle_file_path(instance_name)
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                token = data.get("token")
                site_info = None
                if si := data.get("site_info"):
                    site_info = MoodleSiteInfo(
                        sitename=si.get("sitename", ""),
                        username=si.get("username", ""),
                        fullname=si.get("fullname", ""),
                        userid=si.get("userid", 0),
                        siteurl=si.get("siteurl", ""),
                    )
                return token, site_info
            except Exception:
                pass

        return None, None

    def delete_moodle_token(self, instance_name: str) -> bool:
        """Löscht Moodle Token. Returns True wenn etwas gelöscht wurde."""
        deleted = False

        # Keyring
        try:
            keyring.delete_password(MOODLE_TOKEN_SERVICE, self._moodle_keyring_key(instance_name))
            deleted = True
        except (NoKeyringError, keyring.errors.PasswordDeleteError):
            pass
        except Exception:
            pass

        # Datei
        file_path = self._moodle_file_path(instance_name)
        if file_path.exists():
            try:
                file_path.unlink()
                deleted = True
            except Exception:
                pass

        return deleted

    def has_moodle_token(self, instance_name: str) -> bool:
        """Prüft ob ein Token existiert (ohne es zu laden)."""
        try:
            if keyring.get_password(MOODLE_TOKEN_SERVICE, self._moodle_keyring_key(instance_name)):
                return True
        except Exception:
            pass
        return self._moodle_file_path(instance_name).exists()

    # --- ILIAS Session (für spätere Implementierung) ---

    def _ilias_keyring_key(self, instance_name: str) -> str:
        return f"ilias-session:{instance_name}"

    def _ilias_file_path(self, instance_name: str) -> Path:
        safe_name = instance_name.replace("/", "_").replace(":", "_")
        return self.config_dir / f"ilias_session_{safe_name}.json"

    def save_ilias_session(self, instance_name: str, session: IliasSession) -> None:
        data = {
            "phpsessid": session.phpsessid,
            "il_client_id": session.il_client_id,
            "base_url": session.base_url,
            "client_id": session.client_id,
        }
        try:
            keyring.set_password(ILIAS_SESSION_SERVICE, self._ilias_keyring_key(instance_name), json.dumps(data))
            return
        except (NoKeyringError, Exception):
            pass

        file_path = self._ilias_file_path(instance_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            os.close(fd)
            raise

    def load_ilias_session(self, instance_name: str) -> IliasSession | None:
        try:
            stored = keyring.get_password(ILIAS_SESSION_SERVICE, self._ilias_keyring_key(instance_name))
            if stored:
                data = json.loads(stored)
                return IliasSession(**data)
        except (NoKeyringError, Exception):
            pass

        file_path = self._ilias_file_path(instance_name)
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                return IliasSession(**data)
            except Exception:
                pass
        return None

    def delete_ilias_session(self, instance_name: str) -> bool:
        deleted = False
        try:
            keyring.delete_password(ILIAS_SESSION_SERVICE, self._ilias_keyring_key(instance_name))
            deleted = True
        except (NoKeyringError, keyring.errors.PasswordDeleteError):
            pass
        except Exception:
            pass

        file_path = self._ilias_file_path(instance_name)
        if file_path.exists():
            try:
                file_path.unlink()
                deleted = True
            except Exception:
                pass
        return deleted