"""Exception-Hierarchie der ILIAS-CLI.

Jede Exception bildet auf genau einen dokumentierten Exit-Code ab
(``IliasError.exit_code``). Die CLI fängt ausschließlich ``IliasError``
und übersetzt ihn in den entsprechenden Prozess-Exit-Code.
"""

from __future__ import annotations


class IliasError(Exception):
    """Basisklasse aller Fehler. Standard-Exit-Code: 1 (allgemeiner Fehler)."""

    exit_code: int = 1

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(IliasError):
    """Anmeldung fehlgeschlagen (falsches Passwort, falscher TOTP-Code)."""

    exit_code = 1


class NotLoggedInError(IliasError):
    """Es ist keine Session gespeichert. Exit-Code 2."""

    exit_code = 2


class SessionExpiredError(IliasError):
    """Gespeicherte Session ist abgelaufen. Exit-Code 3."""

    exit_code = 3


class NetworkError(IliasError):
    """Netzwerk- oder Serverfehler. Exit-Code 4."""

    exit_code = 4


class ParserError(IliasError):
    """Unerwartetes HTML / Parser-Fehler. Exit-Code 5."""

    exit_code = 5


class BrowserUnavailableError(IliasError):
    """Das optionale Browser-Extra (Playwright) ist nicht verfügbar."""

    exit_code = 1


class ConfigError(IliasError):
    """Ungültige oder fehlende Konfiguration."""

    exit_code = 1
