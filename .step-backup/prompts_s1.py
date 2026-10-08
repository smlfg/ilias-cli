"""Verdeckte, interaktive Eingaben. Nur von der CLI verwendet, nie vom Core.

Prompts gehen auf stderr, damit ``--json`` auf stdout sauber bleibt.
"""

from __future__ import annotations

import typer


def ask_username(label: str = "Benutzername") -> str:
    return typer.prompt(label, err=True)


def ask_password() -> str:
    return typer.prompt("Passwort", hide_input=True, confirmation_prompt=False, err=True)


def ask_totp() -> str:
    return typer.prompt("TOTP-Code", hide_input=True, confirmation_prompt=False, err=True)
