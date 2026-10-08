"""Fehler der Kernbibliothek mit den Exit-Codes aus INTERFACE.md §3.

0 OK · 1 Login fehlgeschlagen/sonstiges · 2 nicht eingeloggt · 3 Session abgelaufen ·
4 Netzwerk-/Serverfehler · 5 Parser-Fehler.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_AUTH = 1
EXIT_NOT_LOGGED_IN = 2
EXIT_SESSION_EXPIRED = 3
EXIT_NETWORK = 4
EXIT_PARSE = 5


class CoreError(Exception):
    """Basisklasse: trägt eine Meldung für Menschen und den Exit-Code."""

    exit_code: int = EXIT_AUTH
    code: str = "error"

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __repr__(self) -> str:  # pragma: no cover - Diagnose
        return f"{type(self).__name__}({self.message!r})"


class AuthError(CoreError):
    """Zugangsdaten wurden vom Server abgelehnt (Moodle: errorcode invalidlogin)."""

    exit_code = EXIT_AUTH
    code = "auth_failed"


class NotLoggedInError(CoreError):
    """Keine Session für diese Instanz gespeichert."""

    exit_code = EXIT_NOT_LOGGED_IN
    code = "not_logged_in"


class SessionExpiredError(CoreError):
    """Session/Token vorhanden, aber vom Server nicht mehr akzeptiert (invalidtoken)."""

    exit_code = EXIT_SESSION_EXPIRED
    code = "session_expired"


class NetworkError(CoreError):
    """Verbindung fehlgeschlagen oder HTTP >= 500."""

    exit_code = EXIT_NETWORK
    code = "network_error"


class ParseError(CoreError):
    """Unerwartete Antwort (HTML statt JSON, fehlende Felder)."""

    exit_code = EXIT_PARSE
    code = "parse_error"


class ConfigError(CoreError):
    """Unbekannte Instanz, ungültige Konfiguration."""

    exit_code = EXIT_AUTH
    code = "config_error"


class NotSupportedError(CoreError):
    """Backend-Funktion ist (noch) nicht implementiert."""

    exit_code = EXIT_AUTH
    code = "not_supported"
