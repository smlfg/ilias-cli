"""Exception hierarchy mapped to CLI exit codes.

Exit codes (also documented in README.md):
  0 - OK
  1 - general / authentication failure (wrong password, wrong TOTP)
  2 - not logged in (no session stored)
  3 - session expired
  4 - network / server error
  5 - parser error (unexpected HTML)
"""


class IliasError(Exception):
    """Base error with an exit code. Never carries secrets (no password/TOTP/cookies)."""

    exit_code: int = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthFailedError(IliasError):
    """Wrong username/password or wrong TOTP code."""

    exit_code = 1


class NotLoggedInError(IliasError):
    """No session stored."""

    exit_code = 2


class SessionExpiredError(IliasError):
    """Stored session is no longer valid."""

    exit_code = 3


class NetworkError(IliasError):
    """Network or server error (connection, timeout, 5xx, ...)."""

    exit_code = 4


class ParseError(IliasError):
    """Unexpected HTML / parser failure."""

    exit_code = 5


EXIT_CODES = {
    0: "OK",
    1: "Allgemeiner Fehler / Authentifizierung fehlgeschlagen",
    2: "Nicht eingeloggt (keine Session gespeichert)",
    3: "Session abgelaufen",
    4: "Netzwerk-/Serverfehler",
    5: "Parser-Fehler (unerwartetes HTML)",
}
