"""``ilias login`` - headless (httpx) oder mit sichtbarem Browser (--browser)."""

from __future__ import annotations

import json

import typer
from rich.console import Console

from ilias_core.auth import login as core_login
from ilias_core.auth import login_with_browser
from ilias_core.config import load_config
from ilias_core.errors import IliasError
from ilias_core.http import create_client
from ilias_core.session.manager import SessionManager

console = Console()
err_console = Console(stderr=True)


def _prompt_credentials() -> tuple[str, str, str]:
    """Username/Prompt, Passwort und TOTP verdeckt abfragen (nie gespeichert)."""
    username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True)
    totp = typer.prompt("TOTP code", hide_input=True)
    return username, password, totp


def login_command(
    username: str | None = typer.Option(
        None, "--username", "-u", help="HHN-Benutzername (sonst Prompt)"
    ),
    browser: bool = typer.Option(
        False, "--browser", help="Login in einem sichtbaren Browser"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Maschinenlesbare JSON-Ausgabe"
    ),
) -> None:
    """An ILIAS anmelden (HHN-Account + TOTP) und Session speichern."""
    config = load_config()
    try:
        used_username: str | None = None
        if browser:
            result = login_with_browser(config.base_url)
        else:
            if username is None:
                prompted_username, password, totp = _prompt_credentials()
                username = prompted_username
            else:
                password = typer.prompt("Password", hide_input=True)
                totp = typer.prompt("TOTP code", hide_input=True)
            client = create_client()
            result = core_login(
                config.base_url, username, password, totp, client=client
            )
            used_username = username

        manager = SessionManager(config)
        manager.save(result, username=used_username)

        if json_output:
            typer.echo(json.dumps(result.public_dict()))
        else:
            console.print("[green]Login erfolgreich[/green]")
    except IliasError as exc:
        err_console.print(f"[red]Fehler:[/red] {exc}")
        raise typer.Exit(exc.exit_code)
