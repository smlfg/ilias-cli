"""ILIAS-Backend: Adapter über :class:`ilias_core.client.IliasClient`.

Login (OIDC/Keycloak + TOTP für HHN, SAML/Shibboleth für Uni Mannheim), Verifikation
gegen das Dashboard, Session-Cookies im Keyring bzw. in einer 0600-Datei – alles aus
dem bestehenden ILIAS-Kern. Kurse (F2) und Kursinhalt (F3) sind für ILIAS noch nicht
implementiert und liefern einen sauberen ``NotSupportedError`` – nach einem
Session-Check (§4.4, L3).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from ..client import IliasClient
from ..errors import NetworkError, NotLoggedInError, NotSupportedError, SessionExpiredError
from ..http import build_client
from ..models import (
    Course,
    Credentials,
    LoginResult,
    LogoutResult,
    Section,
    SessionStatus,
)
from ..auth.parsers import is_ilias_login_page
from .base import Backend

SESSION_COOKIE_ALLOWLIST = ("PHPSESSID", "ilClientId")


def _request_interval() -> float:
    raw = os.environ.get("ILIAS_CLI_REQUEST_INTERVAL", "1.0")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


class IliasBackend(Backend):
    name = "ilias"
    supports_login = True

    def __init__(self, instance, *, client: IliasClient | None = None) -> None:
        super().__init__(instance)
        self.client = client or IliasClient(instance)

    @property
    def uses_totp(self) -> bool:  # type: ignore[override]
        return self.client.uses_totp

    def login(
        self, credentials: Credentials, otp_callback: Callable[[], str] | None = None
    ) -> LoginResult:
        return self.client.login(credentials.username, credentials.password.reveal(), otp_callback)

    def login_with_browser(self) -> LoginResult:
        return self.client.login_with_browser()

    def status(self) -> SessionStatus:
        return self.client.status()

    def logout(self) -> LogoutResult:
        removed = self.client.logout()
        return LogoutResult(instance=self.instance.key, lms=self.instance.lms, token_removed=removed)

    supports_courses = False

    # -- Session-Check (Spec §4.4, L3) ----------------------------------
    def preflight(self) -> None:
        """Lädt die Session, prüft sie mit einem GET und rotiert ggf. Cookies.

        Reihenfolge: Verbindung (→ 4) → HTTP ≥ 500 (→ 4) → Login-Redirect/-Formular (→ 3).
        """

        cookies = self.client.store.load()
        if not cookies:
            raise NotLoggedInError(
                "Nicht eingeloggt.",
                hint=(
                    f"Mit `ilias login --instance {self.instance.key}` oder "
                    f"`ilias setup --instance {self.instance.key}` anmelden."
                ),
            )
        pause = _request_interval()
        if pause > 0:
            time.sleep(pause)
        http = build_client(self.client.config)
        try:
            host = (urlsplit(self.client.config.base_url).hostname or "").lower()
            for name, value in cookies.items():
                http.cookies.set(name, value, domain=host)
            try:
                response = http.get(
                    f"{self.client.config.normalized_base_url}"
                    "/ilias.php?baseClass=ilmembershipoverviewgui"
                )
            except httpx.HTTPError:
                raise NetworkError("Netzwerkfehler beim Abruf der Kursseite.") from None
            if response.status_code >= 500:
                raise NetworkError(f"Serverfehler (HTTP {response.status_code}).")
            final_url = str(response.url)
            if (
                "login.php" in final_url
                or "cmd=force_login" in final_url
                or is_ilias_login_page(response.text)
            ):
                raise SessionExpiredError(
                    "Session abgelaufen oder nicht mehr gültig.",
                    hint=(
                        f"Erneut mit `ilias login --instance {self.instance.key}` oder "
                        f"`ilias setup --instance {self.instance.key}` anmelden "
                        "(kein automatischer Re-Login)."
                    ),
                )
            rotated = {}
            for name in SESSION_COOKIE_ALLOWLIST:
                value = http.cookies.get(name)
                if value:
                    rotated[name] = value
            if rotated and rotated != cookies:
                self.client.store.save(rotated)
        finally:
            http.close()

    def courses(self) -> list[Course]:
        raise NotSupportedError(
            "Kursliste für ILIAS noch nicht implementiert.",
            hint="Für Moodle: `ilias courses --instance hs-mannheim`.",
        )

    def course_contents(self, course_id: int) -> list[Section]:
        raise NotSupportedError(
            "Kursinhalt (ls) für ILIAS noch nicht implementiert.",
            hint="Für Moodle: `ilias ls <kurs> --instance hs-mannheim`.",
        )
