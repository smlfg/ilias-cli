"""ILIAS-Backend: Adapter über :class:`ilias_core.client.IliasClient`.

Login (OIDC/Keycloak + TOTP für HHN, SAML/Shibboleth für Uni Mannheim), Verifikation
gegen das Dashboard, Session-Cookies im Keyring bzw. in einer 0600-Datei – alles aus
dem bestehenden ILIAS-Kern. Kurse (F2) und Kursinhalt (F3) sind für ILIAS noch nicht
implementiert und liefern einen sauberen ``NotSupportedError``.
"""

from __future__ import annotations

from collections.abc import Callable

from ..client import IliasClient
from ..errors import NotSupportedError
from ..models import (
    Course,
    Credentials,
    LoginResult,
    LogoutResult,
    Section,
    SessionStatus,
)
from ..web import IliasWebSession
from .base import Backend


class IliasBackend(Backend):
    name = "ilias"
    supports_login = True

    def __init__(
        self,
        instance,
        *,
        client: IliasClient | None = None,
        web: IliasWebSession | None = None,
    ) -> None:
        super().__init__(instance)
        self.client = client or IliasClient(instance)
        self.web = web or IliasWebSession(instance)

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

    def prepare_read(self) -> None:
        """Session laden und eine geschützte Seite prüfen (Exit 2/3/4, kein Re-Login)."""

        self.web.get("/ilias.php?baseClass=ilmembershipoverviewgui", label="Session-Prüfung")

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
