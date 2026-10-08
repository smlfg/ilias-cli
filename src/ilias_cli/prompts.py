"""Verdeckte, interaktive Eingaben. Nur von der CLI verwendet, nie vom Core."""

from __future__ import annotations

import typer


def ask_username() -> str:
    return typer.prompt("Benutzername")


def ask_password() -> str:
    return typer.prompt("Passwort", hide_input=True, confirmation_prompt=False)


def ask_totp() -> str:
    return typer.prompt("TOTP-Code", hide_input=True, confirmation_prompt=False)
