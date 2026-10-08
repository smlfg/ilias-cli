"""ILIAS-Backend (Platzhalter).

Der Login-Teil für ILIAS (OIDC/Keycloak + TOTP, INTERFACE.md §6) ist in diesem
Branch nicht implementiert - Ziel ist der Moodle-Login. `status` und `logout`
funktionieren trotzdem, weil der Session-Speicher backend-unabhängig ist.
`courses`/`ls` (F2/F3) gibt es hier bewusst noch nicht: ILIAS hat keine
verallgemeinerbare REST-Schnittstelle (ANFORDERUNGEN.md §4), der Weg dorthin
läuft über Web-Session + HTML-Parsing.
"""

from __future__ import annotations

from ..errors import NotLoggedInError, NotSupportedError
from ..models import (
    CourseListResult,
    Credentials,
    LoginResult,
    LogoutResult,
    SectionNode,
    StatusResult,
)
from ..session import SessionStore
from .base import Backend

_HINT = "In diesem Branch ist nur der Moodle-Login (F1) implementiert."


class IliasBackend(Backend):
    name = "ilias"
    supports_login = False

    def __init__(self, instance) -> None:
        super().__init__(instance)
        self.store = SessionStore(instance.key, instance.lms, instance.base_url)

    def login(self, credentials: Credentials) -> LoginResult:
        raise NotSupportedError(
            f"ILIAS-Login (OIDC/Keycloak) ist nicht implementiert. {_HINT}",
            hint="Für Moodle: `ilias login --instance hs-mannheim`.",
        )

    def status(self) -> StatusResult:
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        raise NotSupportedError(f"ILIAS-Statusprüfung ist nicht implementiert. {_HINT}")

    def logout(self) -> LogoutResult:
        removed = self.store.delete()
        return LogoutResult(instance=self.instance.key, lms=self.instance.lms, token_removed=removed)

    def courses(self) -> CourseListResult:
        raise NotSupportedError(
            f"Kursliste für ILIAS ist für ILIAS noch nicht implementiert. {_HINT}",
            hint="Für Moodle: `ilias courses --instance hs-mannheim`.",
        )

    def course_contents(self, course_id: int) -> tuple[SectionNode, ...]:
        raise NotSupportedError(
            f"Kursinhalt für ILIAS ist für ILIAS noch nicht implementiert. {_HINT}",
            hint="Für Moodle: `ilias ls <kurs> --instance hs-mannheim`.",
        )
