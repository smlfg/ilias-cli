"""Exception-Hierarchie, die auf die Exit-Codes der CLI abbildet.

Exit-Codes (siehe README.md):
    0  OK
    2  nicht eingeloggt
    3  Session abgelaufen
    4  Netzwerk/Server-Fehler
    5  Parser-Fehler (unerwartetes HTML)
"""

from __future__ import annotations


class IliasError(Exception):
    """Basis aller ILIAS-Fehler."""

    exit_code: int = 1

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class NotAuthenticatedError(IliasError):
    """Keine aktive Session (nicht eingeloggt)."""

    exit_code = 2


class AuthenticationError(IliasError):
    """Login fehlgeschlagen (falsches Passwort oder falscher TOTP-Code).

    Der Nutzer ist nach einem fehlgeschlagenen Login nicht eingeloggt,
    daher wird der Exit-Code 2 (nicht eingeloggt) verwendet.
    """

    exit_code = 2


class SessionExpiredError(IliasError):
    """Die gespeicherte Session ist abgelaufen."""

    exit_code = 3


class NetworkError(IliasError):
    """Netzwerk- oder Server-Fehler (httpx.HTTPError)."""

    exit_code = 4


class ParserError(IliasError):
    """Unerwartetes HTML / Struktur nicht erkannt."""

    exit_code = 5


class KeyringUnavailableError(IliasError):
    """Intern: keyring ist nicht importierbar oder hat kein Backend."""

    exit_code = 1


class BrowserLoginError(IliasError):
    """Der Browser-Login (Playwright) ist fehlgeschlagen."""

    exit_code = 1
