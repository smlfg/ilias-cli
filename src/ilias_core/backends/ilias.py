"""ILIAS-Backend: Adapter über :class:`ilias_core.client.IliasClient`.

Login (OIDC/Keycloak + TOTP für HHN, SAML/Shibboleth für Uni Mannheim), Verifikation
gegen das Dashboard, Session-Cookies im Keyring bzw. in einer 0600-Datei – alles aus
dem bestehenden ILIAS-Kern. ``courses`` liest "Meine Kurse und Gruppen" per HTML
(S6); ``course_contents`` (``ls``) folgt in einem späteren Schritt und liefert
weiterhin einen sauberen ``NotSupportedError``.
"""

from __future__ import annotations

from collections.abc import Callable

from ..client import IliasClient
from ..errors import NotSupportedError
from ..ilias_html.fetch import IliasReadClient
from ..ilias_html.membership import parse_memberships
from ..models import (
    Course,
    Credentials,
    LoginResult,
    LogoutResult,
    Section,
    SessionStatus,
)
from .base import Backend

MEMBERSHIP_PATH = "/ilias.php?baseClass=ilmembershipoverviewgui"


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

    supports_courses = True

    def courses(self) -> list[Course]:
        """Kurse und Gruppen aus "Meine Kurse und Gruppen" (HTML, Spec §5)."""

        read = IliasReadClient(self.instance, store=self.client.store)
        response = read.get(MEMBERSHIP_PATH, label="Meine Kurse und Gruppen")
        courses = parse_memberships(response.text, self.base_url)
        courses.sort(key=lambda course: course.sort_key())
        return courses

    def course_contents(self, course_id: int) -> list[Section]:
        raise NotSupportedError(
            "Kursinhalt (ls) für ILIAS noch nicht implementiert.",
            hint="Für Moodle: `ilias ls <kurs> --instance hs-mannheim`.",
        )
