"""Verdeckte, interaktive Eingaben. Nur von der CLI verwendet, nie vom Core.

Prompts gehen auf stderr, damit ``--json`` auf stdout sauber bleibt.
"""

from __future__ import annotations

import typer

from ilias_core.errors import ConfigError


def ask_username(label: str = "Benutzername", default: str | None = None) -> str:
    return typer.prompt(label, default=default, err=True)


def ask_password() -> str:
    return typer.prompt("Passwort", hide_input=True, confirmation_prompt=False, err=True)


def ask_totp() -> str:
    return typer.prompt("TOTP-Code", hide_input=True, confirmation_prompt=False, err=True)


def choose_instance(infos: list) -> str:
    """Interaktive Instanz-Auswahl mit Filter (Spec §3.2).

    Tippen filtert die Liste (case-insensitiver Teilstring wie
    :func:`ilias_core.setup.filter_instances`), eine Nummer übernimmt den
    markierten Treffer, Enter den einzigen verbleibenden. Prompts auf stderr.
    """

    if not infos:
        raise ConfigError("Keine passende Instanz gefunden.")

    current = list(infos)
    while True:
        if len(current) == 1:
            _print_choices(current)
            return current[0].key

        _print_choices(current)
        answer = typer.prompt("Auswahl (Nummer oder Filter)", err=True).strip()
        if not answer:
            if len(current) >= 1:
                return current[0].key
        if answer.isdigit():
            index = int(answer) - 1
            if 0 <= index < len(current):
                return current[index].key
        from ilias_core.setup import filter_instances

        filtered = filter_instances(answer)
        if filtered:
            current = filtered
        elif answer:
            typer.echo(f"Keine Instanz passt auf {answer!r}.", err=True)


def _print_choices(infos: list) -> None:
    typer.echo("Verfügbare Instanzen:", err=True)
    for index, info in enumerate(infos, start=1):
        marker = f"{info.name} ({info.city}), {info.lms}"
        typer.echo(f"  {index}) {info.key} – {marker}", err=True)
