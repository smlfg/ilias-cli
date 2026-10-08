"""ILIAS-Backend: Adapter über :class:`ilias_core.client.IliasClient`.

Login (OIDC/Keycloak + TOTP für HHN, SAML/Shibboleth für Uni Mannheim), Verifikation
gegen das Dashboard, Session-Cookies im Keyring bzw. in einer 0600-Datei – alles aus
dem bestehenden ILIAS-Kern. Kurse (F2) und Kursinhalt (F3) nutzen die HTTP-Grundlage.
"""

from __future__ import annotations

from collections.abc import Callable

from ..client import IliasClient
from ..errors import NetworkError, NotLoggedInError, NotSupportedError, SessionExpiredError
from ..ilias_http import IliasHttpClient
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
        self._http_client: IliasHttpClient | None = None

    @property
    def uses_totp(self) -> bool:  # type: ignore[override]
        return self.client.uses_totp

    def _get_http_client(self) -> IliasHttpClient:
        if self._http_client is None:
            self._http_client = IliasHttpClient(self.instance, self.client.store)
        return self._http_client

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
        http = self._get_http_client()
        try:
            http.get_memberships()
        except NotLoggedInError:
            raise
        except SessionExpiredError:
            raise
        except NetworkError:
            raise
        except Exception as exc:  # noqa: BLE001
            from ..errors import ParserError
            raise ParserError(f"Unerwarteter Fehler beim Laden der Kurse: {type(exc).__name__}") from exc

        # Parse the HTML response - for now return NotSupportedError after session check
        # The actual parsing will be done in S6
        from ..errors import NotSupportedError
        raise NotSupportedError(
            "Kursliste für ILIAS (HTML-Parsing) noch nicht implementiert.",
            hint=f"Session-Prüfung erfolgreich. Parser folgt in S6. Für Moodle: `ilias courses --instance hs-mannheim`.",
        )

    def course_contents(self, course_id: int) -> list[Section]:
        raise NotSupportedError(
            "Kursinhalt (ls) für ILIAS noch nicht implementiert.",
            hint=f"Für Moodle: `ilias ls <kurs> --instance hs-mannheim`.",
        )
