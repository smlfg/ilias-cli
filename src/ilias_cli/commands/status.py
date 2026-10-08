"""``ilias status`` - Session prüfen (0=OK, 2=nicht eingeloggt, 3=abgelaufen)."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from ilias_core.config import load_config
from ilias_core.errors import IliasError
from ilias_core.session.manager import SessionManager

console = Console()
err_console = Console(stderr=True)


def status_command(
    json_output: bool = typer.Option(
        False, "--json", help="Maschinenlesbare JSON-Ausgabe"
    ),
) -> None:
    """Gültigkeit der gespeicherten Session prüfen."""
    config = load_config()
    manager = SessionManager(config)
    try:
        status = manager.check()
    except IliasError as exc:
        err_console.print(f"[red]Fehler:[/red] {exc}")
        raise typer.Exit(exc.exit_code)

    if json_output:
        typer.echo(json.dumps(status.to_dict()))
    else:
        table = Table(title="ILIAS-Session")
        table.add_column("Eigenschaft")
        table.add_column("Wert")
        table.add_row(
            "Status",
            "[green]Eingeloggt[/green]"
            if status.logged_in
            else "[red]Nicht eingeloggt[/red]",
        )
        table.add_row("Basis-URL", status.base_url)
        table.add_row("Client-ID", status.client_id)
        table.add_row("Geprüft am", status.checked_at.isoformat())
        table.add_row("Meldung", status.message)
        console.print(table)

    if not status.logged_in:
        raise typer.Exit(3)
