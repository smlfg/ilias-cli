"""Verdeckte, interaktive Eingaben. Nur von der CLI verwendet, nie vom Core.

Prompts gehen auf stderr, damit ``--json`` auf stdout sauber bleibt.
"""

from __future__ import annotations

import getpass
import sys

import typer

from ilias_core.errors import AbortedError


def ask_username(label: str = "Benutzername") -> str:
    return typer.prompt(label, err=True)


def _hidden(label: str) -> str:
    """Verdeckte Eingabe ohne Echo; im TTY per ``getpass``, sonst von stdin.

    ``getpass`` schaltet das Echo vor der Prompt-Ausgabe ab. Damit kann ein
    Automat nicht versehentlich antworten, bevor die Eingabe bereit ist.
    """

    prompt = f"{label}: "
    try:
        if sys.stdin.isatty():
            return getpass.getpass(prompt, stream=sys.stderr)
        sys.stderr.write(prompt)
        sys.stderr.flush()
        line = sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        raise AbortedError() from None
    if line == "":
        raise AbortedError()
    return line.rstrip("\n")


def ask_password() -> str:
    return _hidden("Passwort")


def ask_totp() -> str:
    return _hidden("TOTP-Code")


def ask_choice(candidates: list[dict]) -> int:
    """Nummerierte Kursauswahl im TTY (Liste auf stderr), liefert die id."""

    for index, candidate in enumerate(candidates, start=1):
        name = candidate.get("fullname") or candidate.get("shortname") or "?"
        short = candidate.get("shortname") or ""
        extra = f" [{short}]" if short else ""
        sys.stderr.write(f"  {index}. {candidate.get('id')}  {name}{extra}\n")
    sys.stderr.write("Auswahl (Nummer): ")
    sys.stderr.flush()
    line = sys.stdin.readline()
    if line == "":
        raise AbortedError()
    text = line.strip()
    if not text:
        raise AbortedError("Abgebrochen.", hint="Nummer aus der Liste eingeben.")
    try:
        number = int(text)
    except ValueError:
        raise AbortedError(
            "Ungültige Auswahl.", hint="Eine Nummer aus der Liste eingeben."
        ) from None
    if not 1 <= number <= len(candidates):
        raise AbortedError(
            "Ungültige Auswahl.", hint=f"Eine Nummer zwischen 1 und {len(candidates)} eingeben."
        )
    return int(candidates[number - 1]["id"])


def ask_yes_no(question: str, *, default: bool = False) -> bool:
    """Bestätigung im TTY: ``<Frage> [j/N]`` auf stderr, Default Nein.

    EOF/Strg+D zählt als Abbruch (kein Schreibzugriff, kein Traceback).
    """

    suffix = " [J/n]" if default else " [j/N]"
    sys.stderr.write(f"{question}{suffix} ")
    sys.stderr.flush()
    line = sys.stdin.readline()
    if line == "":
        raise AbortedError()
    answer = line.strip().lower()
    if not answer:
        return default
    return answer in ("j", "ja", "y", "yes")
