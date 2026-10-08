"""Ausgabe der CLI (menschlich mit rich, maschinell als JSON).

Cookies, Passwörter und Tokens dürfen hier niemals auftauchen.
"""

from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console

from ilias_core.models import LoginResult, SessionStatus

console = Console()
err_console = Console(stderr=True)


def print_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))


def print_login(result: LoginResult) -> None:
    console.print(
        f"[green]Login erfolgreich[/green] "
        f"({result.method}) – {result.base_url} [dim]({result.client_id})[/dim]"
    )


def print_status(status: SessionStatus) -> None:
    console.print(
        f"[green]Eingeloggt[/green] – {status.base_url} [dim]({status.client_id})[/dim]"
    )


def print_logout(removed: bool) -> None:
    if removed:
        console.print("[green]Session gelöscht.[/green]")
    else:
        console.print("Keine gespeicherte Session vorhanden.")


def print_error(message: str) -> None:
    err_console.print(f"[bold red]Fehler:[/bold red] {message}")


def error_payload(exc: Exception, exit_code: int) -> dict[str, Any]:
    return {
        "ok": False,
        "error": type(exc).__name__,
        "exit_code": exit_code,
        "message": str(exc),
    }
