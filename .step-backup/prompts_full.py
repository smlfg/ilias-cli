"""Verdeckte, interaktive Eingaben. Nur von der CLI verwendet, nie vom Core.

Prompts gehen auf stderr, damit ``--json`` auf stdout sauber bleibt.
EOF (Ctrl-D) oder Ctrl-C beim Prompt wird zu einem ``AbortError``
(Exit 1, „Abgebrochen, nichts gespeichert.“).
"""

from __future__ import annotations

import typer

from ilias_core.errors import AbortError

_PROMPT_ERRORS = (EOFError, typer.Abort, KeyboardInterrupt)


def ask_username(label: str = "Benutzername") -> str:
    try:
        return typer.prompt(label, err=True)
    except _PROMPT_ERRORS:
        raise AbortError() from None


def ask_password() -> str:
    try:
        return typer.prompt("Passwort", hide_input=True, confirmation_prompt=False, err=True)
    except _PROMPT_ERRORS:
        raise AbortError() from None


def ask_totp() -> str:
    try:
        return typer.prompt("TOTP-Code", hide_input=True, confirmation_prompt=False, err=True)
    except _PROMPT_ERRORS:
        raise AbortError() from None


def ask_line(label: str, default: str | None = None) -> str:
    try:
        return typer.prompt(label, default=default, err=True)
    except _PROMPT_ERRORS:
        raise AbortError() from None
