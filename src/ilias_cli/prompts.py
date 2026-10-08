"""Verdeckte, interaktive Eingaben. Nur von der CLI verwendet, nie vom Core.

Prompts gehen auf stderr, damit ``--json`` auf stdout sauber bleibt.
"""

from __future__ import annotations

import sys

import typer

from ilias_core.errors import ConfigError


def ask_username(label: str = "Benutzername", default: str | None = None) -> str:
    return typer.prompt(label, default=default, err=True)


def ask_password() -> str:
    return _ask_secret("Passwort")


def ask_totp() -> str:
    return _ask_secret("TOTP-Code")


def _ask_secret(label: str) -> str:
    """Verdeckte Eingabe; ohne Terminal eine Zeile von stdin (Spec §3.3).

    Mit Terminal: verdeckter Prompt (kein Echo). Ohne Terminal (Pipe, CI) wird
    **nicht** ``getpass`` benutzt (das warnt "Password input may be echoed" und
    versucht ``/dev/tty``), sondern genau eine Zeile von stdin gelesen. Die Eingabe
    wird nie ausgegeben oder gespeichert. EOF -> Abbruch (``typer.Abort``).
    """

    if sys.stdin is not None and sys.stdin.isatty():
        return typer.prompt(label, hide_input=True, confirmation_prompt=False, err=True)
    stream = sys.stdin
    typer.echo(f"{label} (stdin, kein Terminal): ", err=True, nl=False)
    line = stream.readline() if stream is not None else ""
    if not line:
        raise typer.Abort()
    typer.echo("", err=True)  # Zeilenende nach dem Prompt; die Eingabe selbst nie ausgeben
    return line.rstrip("\r\n")


def choose_instance(infos: list) -> str:
    """Interaktive Instanz-Auswahl mit Filter (Spec §3.2).

    Tippen filtert die Liste (case-insensitiver Teilstring wie
    :func:`ilias_core.setup.filter_instances`), eine Nummer übernimmt den
    angezeigten Treffer. Bleibt genau ein Treffer übrig, wird er übernommen.
    Enter bei mehreren Treffern wählt **nicht** still den ersten, sondern fragt
    erneut nach einer eindeutigen Auswahl. Prompts auf stderr.
    """

    from ilias_core.setup import filter_instances

    if not infos:
        raise ConfigError(
            "Keine passende Instanz gefunden.",
            hint="`ilias setup --list` zeigt alle Instanzen; dann `ilias setup --instance <key>`.",
        )

    current = list(infos)
    while True:
        _print_choices(current)
        if len(current) == 1:
            return current[0].key

        answer = typer.prompt("Auswahl (Nummer oder Filter)", default="", show_default=False, err=True)
        answer = answer.strip()
        if not answer:
            typer.echo(
                f"Mehrere Treffer ({len(current)}): bitte eine Nummer wählen oder weiter filtern.",
                err=True,
            )
            continue
        if answer.isdigit():
            index = int(answer) - 1
            if 0 <= index < len(current):
                return current[index].key
            typer.echo(f"Ungültige Nummer {answer}: bitte 1 bis {len(current)} wählen.", err=True)
            continue
        filtered = filter_instances(answer)
        if filtered:
            current = filtered
        else:
            typer.echo(f"Keine Instanz passt auf {answer!r}.", err=True)


def _print_choices(infos: list) -> None:
    typer.echo("Verfügbare Instanzen:", err=True)
    for index, info in enumerate(infos, start=1):
        marker = f"{info.name} ({info.city}), {info.lms}"
        typer.echo(f"  {index}) {info.key} – {marker}", err=True)
