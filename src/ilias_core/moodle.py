"""Moodle authentication backend for ilias-core.

Handles the Moodle Mobile web service login flow:
  POST {base}/login/token.php    -> token or error JSON
  POST {base}/webservice/rest/server.php  -> site info (verification)
Token storage: keyring per instance, fallback to 0600 file.
"""

from __future__ import annotations

import json
import os
import getpass
import keyring
import httpx
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MOODLE_LOGIN_URL = "/login/token.php"
MOODLE_WS_URL = "/webservice/rest/server.php"
MOODLE_SERVICE = "moodle_mobile_app"
MOODLE_WSFUNCTION = "core_webservice_get_site_info"
MOODLE_REST_FORMAT = "json"


@dataclass
class MoodleSession:
    """Stored session data per instance."""

    token: str = ""
    fullname: str = ""
    username: str = ""
    sitename: str = ""
    userid: int = 0
    base_url: str = ""
    instance: str = ""


@dataclass
class MoodleConfig:
    """Configuration for a Moodle instance."""

    lms: str = "ilias"
    base_url: str = ""
    instance: str = ""


class MoodleAuthError(Exception):
    """Base exception for Moodle auth errors."""

    pass


class InvalidLoginError(MoodleAuthError):
    """Raised when username/password are invalid."""

    pass


class MoodleAuth:
    """Moodle authentication handler."""

    def __init__(self, config: MoodleConfig) -> None:
        self.config = config
        self.session: Optional[MoodleSession] = None

    # ---- Token storage ------------------------------------------------------

    @staticmethod
    def _keyring_service(instance: str) -> str:
        return f"ilias-cli:moodle:{instance}"

    @staticmethod
    def _token_file(instance: str) -> Path:
        config_dir = Path(os.environ.get("ILIAS_CLI_CONFIG_DIR", Path.home() / ".config" / "ilias-cli"))
        return config_dir / f"moodle_{instance}_token.key"

    def _read_token_from_file(self, instance: str) -> Optional[str]:
        token_file = self._token_file(instance)
        try:
            data = token_file.read_text(encoding="utf-8").strip()
            if data:
                return data
        except FileNotFoundError:
            pass
        return None

    def _write_token_to_file(self, instance: str, token: str) -> None:
        config_dir = Path(os.environ.get("ILIAS_CLI_CONFIG_DIR", Path.home() / ".config" / "ilias-cli"))
        config_dir.mkdir(parents=True, exist_ok=True)
        token_file = self._token_file(instance)
        # Create file with 0600 permissions from the start
        fd = os.open(str(token_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.write(fd, token.encode("utf-8"))
        os.close(fd)

    def _delete_token_file(self, instance: str) -> None:
        token_file = self._token_file(instance)
        try:
            token_file.unlink()
        except FileNotFoundError:
            pass

    def _keyring_get(self, instance: str) -> Optional[str]:
        try:
            return keyring.get_password(self._keyring_service(instance), "")
        except Exception:
            return None

    def _keyring_set(self, instance: str, token: str) -> None:
        keyring.set_password(self._keyring_service(instance), "", token)

    def _keyring_delete(self, instance: str) -> None:
        try:
            keyring.delete_password(self._keyring_service(instance), "")
        except Exception:
            pass

    def load_stored_token(self, instance: str) -> Optional[MoodleSession]:
        """Try to load a stored token (keyring first, then file)."""

        # Try keyring first
        token = self._keyring_get(instance)
        if token is not None:
            session = MoodleSession(
                token=token,
                base_url=self.config.base_url,
                instance=instance,
            )
            self.session = session
            return session

        # Fallback to file
        token = self._read_token_from_file(instance)
        if token is not None:
            session = MoodleSession(
                token=token,
                base_url=self.config.base_url,
                instance=instance,
            )
            self.session = session
            return session

        return None

    def store_token(self, session: MoodleSession) -> None:
        """Store token in keyring or file (0600)."""

        instance = session.instance
        token = session.token

        try:
            self._keyring_set(instance, token)
        except Exception:
            # Keyring failed, fallback to file
            self._write_token_to_file(instance, token)

    def clear_stored_token(self, instance: str) -> None:
        """Clear stored token from keyring and file."""

        self._keyring_delete(instance)
        self._delete_token_file(instance)

    # ---- HTTP helpers -------------------------------------------------------

    @staticmethod
    def _base_url(instance: str, base_url: str, override: str | None = None) -> str:
        if override:
            return override
        return base_url

    def _post_login_token(self, username: str, password: str, base_url: str | None = None) -> dict:
        """POST {base}/login/token.php with username, password, service=moodle_mobile_app."""

        url = self._base_url(base_url or self.config.base_url, base_url) + MOODLE_LOGIN_URL
        payload = {
            "username": username,
            "password": password,
            "service": MOODLE_SERVICE,
        }

        response = httpx.post(url, data=payload, timeout=30.0)
        response.raise_for_status()  # will raise for HTTP >= 5xx

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise MoodleAuthError(f"Unexpected non-JSON response from login: {exc}") from exc

        return data

    def _post_webservice_site_info(self, token: str, base_url: str | None = None) -> dict:
        """POST {base}/webservice/rest/server.php with wstoken, wsfunction, moodlewsrestformat=json."""

        url = self._base_url(base_url or self.config.base_url, base_url) + MOODLE_WS_URL
        payload = {
            "wstoken": token,
            "wsfunction": MOODLE_WSFUNCTION,
            "moodlewsrestformat": MOODLE_REST_FORMAT,
        }

        response = httpx.post(url, data=payload, timeout=30.0)
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise MoodleAuthError(f"Unexpected non-JSON response from webservice: {exc}") from exc

        return data

    # ---- Login flow ---------------------------------------------------------

    def login(self, username: str, password: str, base_url: str | None = None) -> MoodleSession:
        """Perform Moodle login.

        1. POST {base}/login/token.php -> token or error
        2. On success, POST {base}/webservice/rest/server.php -> site info (verification)
        3. On success, store token and return session
        """

        base = self._base_url(base_url or self.config.base_url, base_url)

        # Step 1: Get token from login/token.php
        login_data = self._post_login_token(username, password, base)

        # Check for errors
        if "error" in login_data:
            errorcode = login_data.get("errorcode", "unknown")
            message = login_data.get("error", "Login failed")
            raise InvalidLoginError(
                f"Moodle login failed (errorcode={errorcode}): {message}"
            )

        # Step 2: Verify with webservice/rest/server.php
        if "token" not in login_data:
            raise MoodleAuthError("No token received from Moodle login/token.php")

        token = login_data["token"]
        ws_data = self._post_webservice_site_info(token, base)

        # Step 3: Verify site info response
        if "error" in ws_data:
            # Invalid token or similar
            raise InvalidLoginError(
                f"Moodle site info verification failed: {ws_data.get('error', 'unknown error')}"
            )

        # Build session from verified data
        session = MoodleSession(
            token=token,
            fullname=ws_data.get("fullname", ""),
            username=ws_data.get("username", ""),
            sitename=ws_data.get("sitename", ""),
            userid=ws_data.get("userid", 0),
            base_url=base,
            instance=self.config.instance,
        )

        self.session = session
        return session

    # ---- Status check -------------------------------------------------------

    def check_status(self, session: Optional[MoodleSession] = None) -> MoodleSession:
        """Verify stored token is still valid by checking site info."""

        s = session or self.session
        if s is None or not s.token:
            raise InvalidLoginError("No stored session (log in first)")

        base = self._base_url(s.base_url, base_url=None)

        try:
            ws_data = self._post_webservice_site_info(s.token, base)
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code >= 500:
                raise MoodleAuthError("Moodle server error") from exc
            raise InvalidLoginError("Invalid/malformed server response") from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise InvalidLoginError("Unexpected response format from Moodle") from exc

        # Check for invalid token error
        if "error" in ws_data:
            raise InvalidLoginError("Session invalid (token expired)") from exc

        # Update session with fresh data
        s.fullname = ws_data.get("fullname", s.fullname)
        s.username = ws_data.get("username", s.username)
        s.sitename = ws_data.get("sitename", s.sitename)
        s.userid = ws_data.get("userid", s.userid)
        return s

    # ---- Logout -------------------------------------------------------------

    def logout(self, instance: str | None = None) -> None:
        """Clear stored token locally."""

        inst = instance or self.config.instance or ""
        self.clear_stored_token(inst)
        self.session = MoodleSession()