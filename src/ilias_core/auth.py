"""Eingabe der Zugangsdaten (A1).

- Kein `--password`-Flag: das Passwort wird nur verdeckt abgefragt.
- Ohne TTY (Tests, Pipes) wird die Zeile von stdin gelesen, der Prompt geht nach stderr,
  damit `--json` auf stdout genau ein JSON-Objekt bleibt.
- Das Passwort wird als `Secret` weitergegeben (`repr()` = `***`) und nie ausgegeben.
"""

from __future__ import annotations

import getpass
import sys
from typing import TextIO

from .errors import AuthError
from .models import Credentials
from .secrets import Secret

USERNAME_PROMPT = "Benutzername: "
PASSWORD_PROMPT = "Passwort: "


def _isatty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):  # pragma: no cover - geschlossene Streams
        return False


def _prompt_to_stderr(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


def prompt_username(prompt: str = USERNAME_PROMPT, stream: TextIO | None = None) -> str:
    stream = stream or sys.stdin
    _prompt_to_stderr(prompt)
    line = stream.readline()
    if line == "":  # EOF
        raise AuthError("Kein Benutzername eingegeben (stdin leer).")
    return line.strip()


def prompt_password(prompt: str = PASSWORD_PROMPT, stream: TextIO | None = None) -> Secret:
    """Verdeckte Eingabe: TTY -> getpass, sonst stille Zeile von stdin."""
    stream = stream or sys.stdin
    if _isatty(sys.stdin) and _isatty(sys.stderr):
        return Secret(getpass.getpass(prompt))
    _prompt_to_stderr(prompt)
    line = stream.readline()
    if line == "":
        raise AuthError("Kein Passwort eingegeben (stdin leer).")
    return Secret(line.rstrip("\r\n"))


def prompt_credentials(
    username_prompt: str = USERNAME_PROMPT,
    password_prompt: str = PASSWORD_PROMPT,
    stream: TextIO | None = None,
) -> Credentials:
    username = prompt_username(username_prompt, stream)
    if not username:
        raise AuthError("Benutzername darf nicht leer sein.")
    password = prompt_password(password_prompt, stream)
    if not password:
        raise AuthError("Passwort darf nicht leer sein.")
    return Credentials(username=username, password=password)
