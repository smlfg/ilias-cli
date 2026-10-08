"""Fehlerklassen mit den Exit-Codes aus INTERFACE.md.

Wichtig (A1/A4): Fehlermeldungen dürfen niemals Passwort, TOTP oder Token
enthalten. Die Konstruktoren erhalten deshalb nur bereits bereinigte Texte.
"""

from __future__ import annotations


class IliasCliError(Exception):
    """Basisklasse. Exit 1 = sonstiger Fehler / abgelehnter Login."""

    exit_code = 1
    errorcode = "error"


class AuthError(IliasCliError):
    """Login abgelehnt (falscher Benutzername/Passwort)."""

    exit_code = 1
    errorcode = "invalidlogin"


class NotLoggedInError(IliasCliError):
    """Kein gespeicherter Token vorhanden."""

    exit_code = 2
    errorcode = "not_logged_in"


class SessionExpiredError(IliasCliError):
    """Gespeicherter Token ist ungültig/abgelaufen."""

    exit_code = 3
    errorcode = "invalidtoken"


class NetworkError(IliasCliError):
    """Verbindungsfehler oder HTTP >= 500."""

    exit_code = 4
    errorcode = "network_error"


class UnexpectedResponseError(IliasCliError):
    """Unerwartete Antwort (kein JSON, unerwartetes HTML etc.)."""

    exit_code = 5
    errorcode = "unexpected_response"
