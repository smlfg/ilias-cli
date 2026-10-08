"""``ilias logout`` - gespeicherte Session löschen."""

from __future__ import annotations

import json

import typer
from rich.console import Console

from ilias_core.config import load_config
from ilias_core.errors import IliasError, NotAuthenticatedError
from ilias_core.session.manager import SessionManager

console = Console()
err_console = Console(stderr=True)


def logout_command(
    json_output: bool = typer.Option(
        False, "--json", help="Maschinenlesbare JSON-Ausgabe"
    ),
) -> None:
    """Gespeicherte Session löschen."""
    config = load_config()
    manager = SessionManager(config)
    try:
        if manager.load() is None:
            raise NotAuthenticatedError("Keine aktive Session - nichts zu tun")
        manager.delete()
        if json_output:
            typer.echo(json.dumps({"logged_in": False, "message": "Ausgeloggt"}))
        else:
            console.print("[green]Ausgeloggt[/green]")
    except IliasError as exc:
        err_console.print(f"[red]Fehler:[/red] {exc}")
        raise typer.Exit(exc.exit_code)
