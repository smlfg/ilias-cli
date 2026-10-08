"""Exceptions mit Exit-Codes gemäß INTERFACE.md."""

from __future__ import annotations


class IliasCliError(Exception):
    """Basis-Exception mit Exit-Code."""

    exit_code: int = 1

    def __init__(self, message: str, *, exit_code: int | None = None, errorcode: str | None = None):
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code
        self.errorcode = errorcode


class AuthError(IliasCliError):
    """Authentifizierungsfehler (falsches Passwort, ungültiges Token, etc.) -> Exit 1/2."""

    exit_code = 1


class NotLoggedInError(IliasCliError):
    """Keine gespeicherte Session/Token -> Exit 2."""

    exit_code = 2


class SessionExpiredError(IliasCliError):
    """Session/Token abgelaufen/ungültig -> Exit 3."""

    exit_code = 3


class NetworkError(IliasCliError):
    """Netzwerkfehler, Server nicht erreichbar, HTTP >= 500 -> Exit 4."""

    exit_code = 4


class ParseError(IliasCliError):
    """Parser-Fehler: unerwartete Antwort (HTML statt JSON, etc.) -> Exit 5."""

    exit_code = 5


class ConfigError(IliasCliError):
    """Konfigurationsfehler."""

    exit_code = 1


# Moodle-spezifische Fehler-Codes
MOODLE_ERROR_CODES = {
    "invalidlogin": "Ungültige Anmeldedaten (Benutzername oder Passwort falsch)",
    "invalidtoken": "Token ungültig oder abgelaufen",
    "accessexception": "Zugriff verweigert",
    "requireslogin": "Anmeldung erforderlich",
}


def moodle_error_to_exception(errorcode: str, message: str | None = None) -> IliasCliError:
    """Wandelt Moodle errorcode in passende Exception um."""
    if errorcode == "invalidlogin":
        return AuthError(message or MOODLE_ERROR_CODES.get(errorcode, "Ungültige Anmeldedaten"), errorcode=errorcode)
    if errorcode == "invalidtoken":
        return SessionExpiredError(message or MOODLE_ERROR_CODES.get(errorcode, "Token ungültig"), errorcode=errorcode)
    if errorcode in ("accessexception", "requireslogin"):
        return SessionExpiredError(message or MOODLE_ERROR_CODES.get(errorcode, "Zugriff verweigert"), errorcode=errorcode)
    return AuthError(message or f"Moodle-Fehler: {errorcode}", errorcode=errorcode)