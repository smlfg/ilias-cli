from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ilias_core import __version__, auth, config, session
from ilias_core.errors import IliasCliError, NotLoggedInError, SessionExpiredError

app = typer.Typer(help="ILIAS-CLI (Login, Status, Logout)", no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


def _fail(exc: IliasCliError, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps({"ok": False, "error": exc.message, "exit_code": exc.exit_code}))
    else:
        err_console.print(f"[red]Fehler:[/red] {exc.message}")
    raise typer.Exit(code=exc.exit_code)


@app.command()
def login(
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbare Ausgabe"),
    browser: bool = typer.Option(False, "--browser", help="Login in sichtbarem Browser"),
) -> None:
    cfg = config.load_config()
    try:
        if browser:
            from ilias_core import browser_auth

            data = browser_auth.login_with_browser(cfg.base_url)
        else:
            username = typer.prompt("Benutzername")
            password = typer.prompt("Passwort", hide_input=True)
            data = auth.login(
                cfg.base_url,
                username,
                password,
                lambda: typer.prompt("TOTP-Code (Authenticator-App)"),
            )
        storage = session.save_session(data)
    except IliasCliError as exc:
        _fail(exc, json_output)
    if json_output:
        typer.echo(json.dumps({"ok": True, "base_url": data.base_url, "storage": storage, "created_at": data.created_at.isoformat()}))
    else:
        console.print(f"[green]Eingeloggt[/green] bei {data.base_url} (Session im {storage} gespeichert).")


@app.command()
def status(json_output: bool = typer.Option(False, "--json", help="Maschinenlesbare Ausgabe")) -> None:
    cfg = config.load_config()
    try:
        data = session.load_session()
        if data is None:
            raise NotLoggedInError("Keine Session gespeichert. Bitte 'ilias login' ausführen.")
        if data.base_url.rstrip("/") != cfg.base_url.rstrip("/"):
            raise NotLoggedInError(f"Session gehört zu {data.base_url}, Konfiguration zu {cfg.base_url}.")
        status_data = session.check_session(data)
    except IliasCliError as exc:
        _fail(exc, json_output)
    if json_output:
        typer.echo(json.dumps({"ok": True, "logged_in": True, "base_url": status_data.base_url, "checked_at": status_data.checked_at.isoformat()}))
    else:
        table = Table(title="ILIAS-Status")
        table.add_column("Eigenschaft")
        table.add_column("Wert")
        table.add_row("Eingeloggt", "ja")
        table.add_row("Basis-URL", status_data.base_url)
        console.print(table)


@app.command()
def logout(json_output: bool = typer.Option(False, "--json", help="Maschinenlesbare Ausgabe")) -> None:
    try:
        session.delete_session()
    except Exception as exc:  # pragma: no cover
        _fail(IliasCliError(str(exc)), json_output)
    if json_output:
        typer.echo(json.dumps({"ok": True, "action": "logout"}))
    else:
        console.print("Session gelöscht.")


@app.callback()
def main(version: bool = typer.Option(False, "--version", help="Version anzeigen")) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()
