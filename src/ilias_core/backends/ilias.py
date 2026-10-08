"""ILIAS-Backend: Adapter über :class:`ilias_core.client.IliasClient`.

Login (OIDC/Keycloak + TOTP für HHN, SAML/Shibboleth für Uni Mannheim), Verifikation
gegen das Dashboard, Session-Cookies im Keyring bzw. in einer 0600-Datei – alles aus
dem bestehenden ILIAS-Kern. Kurse (F2) und Kursinhalt (F3) werden per HTML-Scraping
implementiert.
"""

from __future__ import annotations

from collections.abc import Callable

from ..client import IliasClient
from ..errors import NotSupportedError, ParserError
from ..models import (
    Course,
    Credentials,
    LoginResult,
    LogoutResult,
    Section,
    SessionStatus,
)
from ..ilias_html import fetch_page, parse_memberships, has_empty_membership_hint, has_login_marker
from .base import Backend


class IliasBackend(Backend):
    name = "ilias"
    supports_login = True
    supports_courses = True

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

    def courses(self) -> list[Course]:
        """Kurse aus 'Meine Kurse und Gruppen' (ilmembershipoverviewgui) laden.

        Spec §5.2, §13.2: Nur GET, Session wiederverwenden, Status/Redirect prüfen.
        """
        result = fetch_page(self.instance, "/ilias.php?baseClass=ilmembershipoverviewgui", page_type="membership")

        html = result.html

        # Leere Mitgliedschaft mit Hinweis -> leere Liste, Exit 0
        if has_empty_membership_hint(html):
            return []

        # Seite ohne Liste, ohne Leer-Hinweis, aber mit Login-Merkmal -> Exit 5
        if has_login_marker(html):
            from ..errors import SessionExpiredError
            raise SessionExpiredError(
                "Session abgelaufen (Login-Merkmal in der Kursliste erkannt).",
                hint=f"`ilias login --instance {self.instance.key}` oder `ilias setup --instance {self.instance.key}` ausführen.",
            )

        # Mitgliedschaften parsen
        courses = parse_memberships(html, self.instance.normalized_base_url)

        # Leere Liste ohne Hinweis und ohne Login-Merkmal -> Exit 5
        if not courses:
            raise ParserError(
                "Keine Kurse gefunden und keine Leer-Hinweis/Kein Login-Merkmal (unerwartete Seite).",
                hint="ILIAS-Seitenstruktur hat sich möglicherweise geändert.",
            )

        return courses

    def course_contents(self, course_id: int) -> list[Section]:
        raise NotSupportedError(
            "Kursinhalt (ls) für ILIAS noch nicht implementiert.",
            hint="Für Moodle: `ilias ls <kurs> --instance hs-mannheim`.",
        )
