"""Strukturierte Fehler mit Exit-Code (INTERFACE.md §3)."""

from __future__ import annotations


class CliError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class AuthError(CliError):
    def __init__(self, message: str = "Login fehlgeschlagen"):
        super().__init__(message, exit_code=1)


class NotLoggedInError(CliError):
    def __init__(self, message: str = "Nicht eingeloggt"):
        super().__init__(message, exit_code=2)


class SessionExpiredError(CliError):
    def __init__(self, message: str = "Session abgelaufen"):
        super().__init__(message, exit_code=3)


class NetworkError(CliError):
    def __init__(self, message: str = "Netzwerk-/Serverfehler"):
        super().__init__(message, exit_code=4)


class ParserError(CliError):
    def __init__(self, message: str = "Unerwartete Antwort vom Server"):
        super().__init__(message, exit_code=5)
