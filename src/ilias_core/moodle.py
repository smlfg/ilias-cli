"""Moodle Backend: Login via Mobile Web Service, Status, Logout."""

from __future__ import annotations

import httpx
from httpx import HTTPStatusError, RequestError, TimeoutException

from .config import InstanceProfile
from .exceptions import AuthError, NetworkError, ParseError, SessionExpiredError, moodle_error_to_exception
from .models import LoginResult, LogoutResult, MoodleSiteInfo, MoodleTokenResponse, StatusResult
from .session import SessionStore


class MoodleBackend:
    """Moodle Backend Implementation."""

    def __init__(self, instance: InstanceProfile, config_dir: str | None = None):
        self.instance = instance
        self.base_url = instance.base_url.rstrip("/")
        self.session_store = SessionStore(Path(config_dir) if config_dir else None)
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "ilias-cli/0.0.0"},
        )

    def login(self, username: str, password: str) -> LoginResult:
        """Login via Moodle Mobile Web Service."""
        # 1. Token anfordern
        token_resp = self._get_token(username, password)

        if token_resp.is_error():
            if token_resp.errorcode:
                raise moodle_error_to_exception(token_resp.errorcode, token_resp.error)
            raise AuthError(token_resp.error or "Unbekannter Login-Fehler")

        token = token_resp.token
        if not token:
            raise ParseError("Leeres Token in Antwort")

        # 2. Token verifizieren via core_webservice_get_site_info
        site_info = self._verify_token(token)

        # 3. Token + Site-Info speichern
        self.session_store.save_moodle_token(self.instance.name, token, site_info)

        return LoginResult(
            success=True,
            instance_name=self.instance.name,
            lms="moodle",
            base_url=self.base_url,
            username=site_info.username,
            fullname=site_info.fullname,
            sitename=site_info.sitename,
            token=token,
            exit_code=0,
        )

    def _get_token(self, username: str, password: str) -> MoodleTokenResponse:
        """POST /login/token.php mit username, password, service=moodle_mobile_app."""
        url = f"{self.base_url}/login/token.php"
        data = {
            "username": username,
            "password": password,
            "service": "moodle_mobile_app",
        }

        try:
            resp = self.client.post(url, data=data)
            resp.raise_for_status()
        except TimeoutException as e:
            raise NetworkError(f"Timeout bei Token-Anfrage: {e}") from e
        except RequestError as e:
            raise NetworkError(f"Netzwerkfehler bei Token-Anfrage: {e}") from e
        except HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise NetworkError(f"Serverfehler {e.response.status_code}: {e}") from e
            # 4xx wird unten als ParseError behandelt

        # Antwort parsen (sollte JSON sein)
        try:
            data = resp.json()
        except Exception as e:
            # Unerwartete Antwort (HTML, etc.)
            raise ParseError(f"Unerwartete Antwort von /login/token.php: {resp.text[:200]}") from e

        return MoodleTokenResponse.from_json(data)

    def _verify_token(self, token: str) -> MoodleSiteInfo:
        """POST /webservice/rest/server.php mit wstoken, wsfunction=core_webservice_get_site_info."""
        url = f"{self.base_url}/webservice/rest/server.php"
        params = {
            "wstoken": token,
            "wsfunction": "core_webservice_get_site_info",
            "moodlewsrestformat": "json",
        }

        try:
            resp = self.client.post(url, params=params)
            resp.raise_for_status()
        except TimeoutException as e:
            raise NetworkError(f"Timeout bei Site-Info: {e}") from e
        except RequestError as e:
            raise NetworkError(f"Netzwerkfehler bei Site-Info: {e}") from e
        except HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise NetworkError(f"Serverfehler {e.response.status_code}: {e}") from e

        try:
            data = resp.json()
        except Exception as e:
            raise ParseError(f"Unerwartete Antwort von core_webservice_get_site_info: {resp.text[:200]}") from e

        site_info = MoodleSiteInfo.from_json(data)

        if site_info.is_error():
            if site_info.is_invalid_token():
                raise SessionExpiredError("Token ungültig (invalidtoken)")
            raise AuthError(site_info.message or f"Moodle-Fehler: {site_info.errorcode}")

        return site_info

    def status(self) -> StatusResult:
        """Prüft gespeicherten Token via core_webservice_get_site_info."""
        token, cached_site_info = self.session_store.load_moodle_token(self.instance.name)

        if not token:
            return StatusResult(
                success=False,
                instance_name=self.instance.name,
                lms="moodle",
                base_url=self.base_url,
                logged_in=False,
                token_valid=False,
                error="Kein Token gespeichert",
                errorcode="not_logged_in",
                exit_code=2,
            )

        try:
            site_info = self._verify_token(token)
            return StatusResult(
                success=True,
                instance_name=self.instance.name,
                lms="moodle",
                base_url=self.base_url,
                logged_in=True,
                token_valid=True,
                username=site_info.username,
                fullname=site_info.fullname,
                sitename=site_info.sitename,
                exit_code=0,
            )
        except SessionExpiredError:
            # Token ungültig -> lokal löschen und Exit 3
            self.session_store.delete_moodle_token(self.instance.name)
            return StatusResult(
                success=False,
                instance_name=self.instance.name,
                lms="moodle",
                base_url=self.base_url,
                logged_in=False,
                token_valid=False,
                error="Token abgelaufen oder ungültig",
                errorcode="invalidtoken",
                exit_code=3,
            )
        except NetworkError:
            return StatusResult(
                success=False,
                instance_name=self.instance.name,
                lms="moodle",
                base_url=self.base_url,
                logged_in=False,
                token_valid=False,
                error="Netzwerkfehler",
                errorcode="network_error",
                exit_code=4,
            )
        except ParseError as e:
            return StatusResult(
                success=False,
                instance_name=self.instance.name,
                lms="moodle",
                base_url=self.base_url,
                logged_in=False,
                token_valid=False,
                error=f"Parser-Fehler: {e}",
                errorcode="parse_error",
                exit_code=5,
            )
        except AuthError as e:
            return StatusResult(
                success=False,
                instance_name=self.instance.name,
                lms="moodle",
                base_url=self.base_url,
                logged_in=False,
                token_valid=False,
                error=str(e),
                errorcode="auth_error",
                exit_code=1,
            )

    def logout(self) -> LogoutResult:
        """Löscht gespeicherten Token lokal."""
        had_session = self.session_store.has_moodle_token(self.instance.name)
        self.session_store.delete_moodle_token(self.instance.name)

        return LogoutResult(
            success=True,
            instance_name=self.instance.name,
            lms="moodle",
            base_url=self.base_url,
            had_session=had_session,
            exit_code=0,
        )

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()