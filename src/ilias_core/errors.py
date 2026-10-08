"""Fehler mit Exit-Codes (siehe INTERFACE.md §3)."""

from __future__ import annotations


class CliError(Exception):
    exit_code: int = 1
    error_key: str = "error"

    def __init__(self, message: str, *, error_key: str | None = None) -> None:
        super().__init__(message)
        if error_key:
            self.error_key = error_key


class AuthFailedError(CliError):
    exit_code = 1
    error_key = "invalid_login"


class NotLoggedInError(CliError):
    exit_code = 2
    error_key = "not_logged_in"


class SessionExpiredError(CliError):
    exit_code = 3
    error_key = "expired"


class NetworkError(CliError):
    exit_code = 4
    error_key = "network_error"


class ParseError(CliError):
    exit_code = 5
    error_key = "parse_error"
