"""ILIAS-Backend: Adapter über :class:`ilias_core.client.IliasClient`.

Login (OIDC/Keycloak + TOTP für HHN, SAML/Shibboleth für Uni Mannheim), Verifikation
gegen das Dashboard, Session-Cookies im Keyring bzw. in einer 0600-Datei – alles aus
dem bestehenden ILIAS-Kern. Kurse (F2) und Kursinhalt (F3) sind für ILIAS noch nicht
implementiert und liefern einen sauberen ``NotSupportedError``.
"""

from __future__ import annotations

from collections.abc import Callable

from ..client import IliasClient
from ..errors import NotSupportedError, ParserError
from ..ilias_html.fetch import IliasFetcher
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
        fetcher = IliasFetcher(self.client.config)
        label = "Kursliste"
        try:
            html_text = fetcher.get_text("/ilias.php?baseClass=ilmembershipoverviewgui", label=label)
        except ParserError:
            raise
        try:
            courses = parse_memberships(html_text, self.client.config.normalized_base_url)
        except ParserError as exc:
            raise ParserError(
                f"{exc.message} Seite: Mitgliedschaften (Meine Kurse und Gruppen), "
                f"URL: {self.client.config.normalized_base_url}/ilias.php",
                hint=(
                    f"Erwartet wurde die Kursliste von `ilias courses --instance {self.instance.key}`. "
                    "Evtl. Wartungsarbeiten oder ein geändertes HHN-Markup."
                ),
            ) from None
        courses.sort(key=lambda course: course.sort_key())
        return courses

    def course_contents(self, course_id: int) -> list[Section]:
        raise NotSupportedError(
            "Kursinhalt (ls) für ILIAS noch nicht implementiert.",
            hint=f"Noch nicht verfügbar: `ilias ls --instance {self.instance.key}`; für Moodle: `ilias ls <kurs> --instance hs-mannheim`.",
        )
