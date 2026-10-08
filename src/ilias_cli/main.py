"""Dünne CLI-Hülle für ILIAS/Moodle Backend."""

from __future__ import annotations

import getpass
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ilias_core import (
    AuthError,
    Config,
    LoginResult,
    LogoutResult,
    NetworkError,
    NotLoggedInError,
    ParseError,
    SessionExpiredError,
    StatusResult,
    create_backend,
    get_config_dir,
)
from ilias_core.config import InstanceProfile

app = typer.Typer(
    help="ILIAS/Moodle CLI für Hochschulen",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console(stderr=True)


def _get_instance_name(instance: str | None) -> str:
    """Ermittelt den Instanz-Namen (CLI > Config > Default)."""
    return instance or "hs-mannheim"


def _get_config_dir(config_dir: str | None) -> Path | None:
    if config_dir:
        return Path(config_dir)
    return None


def _load_config(instance: str | None, config_dir: str | None) -> tuple[Config, InstanceProfile]:
    """Lädt Config und gibt das Instanz-Profil zurück."""
    cfg = Config.load(_get_config_dir(config_dir))
    instance_name = _get_instance_name(instance)
    profile = cfg.get_instance(instance_name)
    return cfg, profile


def _print_result_json(result: LoginResult | StatusResult | LogoutResult) -> None:
    """Gibt Ergebnis als JSON aus (auf stdout)."""
    import json

    if isinstance(result, LoginResult):
        print(json.dumps(result.to_json(), ensure_ascii=False))
    elif isinstance(result, StatusResult):
        print(json.dumps(result.to_json(), ensure_ascii=False))
    elif isinstance(result, LogoutResult):
        print(json.dumps(result.to_json(), ensure_ascii=False))


def _print_result_human(result: LoginResult | StatusResult | LogoutResult) -> None:
    """Gibt Ergebnis als menschenlesbare Tabelle aus (auf stderr)."""
    if isinstance(result, LoginResult):
        if result.success:
            console.print(f"[green]✓[/green] Angemeldet als [bold]{result.fullname}[/bold] (@{result.username})")
            console.print(f"  Instanz: {result.instance_name} ({result.lms})")
            console.print(f"  Plattform: {result.sitename}")
            console.print(f"  URL: {result.base_url}")
        else:
            console.print(f"[red]✗[/red] Login fehlgeschlagen: {result.error}")
            if result.errorcode:
                console.print(f"  Fehlercode: {result.errorcode}")

    elif isinstance(result, StatusResult):
        if result.success and result.logged_in:
            console.print(f"[green]✓[/green] Eingeloggt als [bold]{result.fullname}[/bold] (@{result.username})")
            console.print(f"  Instanz: {result.instance_name} ({result.lms})")
            console.print(f"  Plattform: {result.sitename}")
            console.print(f"  URL: {result.base_url}")
            if result.last_checked:
                console.print(f"  Geprüft: {result.last_checked.isoformat()}")
        else:
            console.print(f"[yellow]![/yellow] Nicht eingeloggt: {result.error or 'Keine Session'}")
            if result.errorcode:
                console.print(f"  Code: {result.errorcode}")

    elif isinstance(result, LogoutResult):
        if result.had_session:
            console.print(f"[green]✓[/red] Abgemeldet von {result.instance_name} ({result.lms})")
        else:
            console.print(f"[yellow]![/yellow] Keine Session vorhanden bei {result.instance_name}")


def _prompt_username() -> str:
    return typer.prompt("Benutzername", prompt_suffix=": ")


def _prompt_password() -> str:
    return getpass.getpass("Passwort: ")


def _handle_exception(e: Exception, json_output: bool) -> int:
    """Behandelt Exceptions und gibt passenden Exit-Code zurück."""
    if isinstance(e, (AuthError, NotLoggedInError, SessionExpiredError, NetworkError, ParseError)):
        if json_output:
            # Minimal JSON für Fehler
            import json

            print(json.dumps({"success": False, "error": str(e), "exit_code": e.exit_code}, ensure_ascii=False))
        else:
            console.print(f"[red]Fehler:[/red] {e}")
        return e.exit_code

    # Unerwarteter Fehler
    if json_output:
        import json

        print(json.dumps({"success": False, "error": "Interner Fehler", "exit_code": 1}, ensure_ascii=False))
    else:
        console.print(f"[red]Interner Fehler:[/red] {e}")
    return 1


@app.command()
def login(
    instance: Annotated[str | None, typer.Option("--instance", "-i", help="Instanz-Profil (z. B. hs-mannheim)")] = None,
    config_dir: Annotated[str | None, typer.Option("--config-dir", help="Konfigurationsverzeichnis")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Base-URL überschreiben")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON-Ausgabe")] = False,
) -> None:
    """Login mit Benutzername/Passwort (Moodle) oder OIDC+TOTP (ILIAS)."""
    try:
        cfg, profile = _load_config(instance, config_dir)

        # Base URL Override
        if base_url:
            profile.base_url = base_url.rstrip("/")

        username = _prompt_username()
        password = _prompt_password()

        with create_backend(profile, config_dir) as backend:
            # Für Moodle: kein TOTP, für ILIAS: TOTP abfragen
            if profile.lms == "moodle":
                result = backend.login(username, password)
            else:
                totp = typer.prompt("TOTP-Code", prompt_suffix=": ", hide_input=True)
                result = backend.login(username, password, totp=totp)

        if json_output:
            _print_result_json(result)
        else:
            _print_result_human(result)

        raise typer.Exit(code=result.exit_code)

    except typer.Exit:
        raise
    except Exception as e:
        raise typer.Exit(code=_handle_exception(e, json_output))


@app.command()
def status(
    instance: Annotated[str | None, typer.Option("--instance", "-i", help="Instanz-Profil (z. B. hs-mannheim)")] = None,
    config_dir: Annotated[str | None, typer.Option("--config-dir", help="Konfigurationsverzeichnis")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Base-URL überschreiben")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON-Ausgabe")] = False,
) -> None:
    """Prüft ob eine gültige Session/Token existiert."""
    try:
        cfg, profile = _load_config(instance, config_dir)

        if base_url:
            profile.base_url = base_url.rstrip("/")

        with create_backend(profile, config_dir) as backend:
            result = backend.status()
            result.last_checked = datetime.now()

        if json_output:
            _print_result_json(result)
        else:
            _print_result_human(result)

        raise typer.Exit(code=result.exit_code)

    except typer.Exit:
        raise
    except Exception as e:
        raise typer.Exit(code=_handle_exception(e, json_output))


@app.command()
def logout(
    instance: Annotated[str | None, typer.Option("--instance", "-i", help="Instanz-Profil (z. B. hs-mannheim)")] = None,
    config_dir: Annotated[str | None, typer.Option("--config-dir", help="Konfigurationsverzeichnis")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Base-URL überschreiben")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON-Ausgabe")] = False,
) -> None:
    """Löscht lokale Session/Token."""
    try:
        cfg, profile = _load_config(instance, config_dir)

        if base_url:
            profile.base_url = base_url.rstrip("/")

        with create_backend(profile, config_dir) as backend:
            result = backend.logout()

        if json_output:
            _print_result_json(result)
        else:
            _print_result_human(result)

        raise typer.Exit(code=result.exit_code)

    except typer.Exit:
        raise
    except Exception as e:
        raise typer.Exit(code=_handle_exception(e, json_output))


@app.command()
def config_show(
    instance: Annotated[str | None, typer.Option("--instance", "-i", help="Instanz-Profil anzeigen")] = None,
    config_dir: Annotated[str | None, typer.Option("--config-dir", help="Konfigurationsverzeichnis")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON-Ausgabe")] = False,
) -> None:
    """Zeigt die aktuelle Konfiguration."""
    try:
        cfg = Config.load(_get_config_dir(config_dir))
        instance_name = _get_instance_name(instance)
        profile = cfg.get_instance(instance_name)

        if json_output:
            import json

            print(
                json.dumps(
                    {
                        "default_instance": cfg.default_instance,
                        "current_instance": instance_name,
                        "base_url": profile.base_url,
                        "lms": profile.lms,
                        "client_id": profile.client_id,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            table = Table(title="ILIAS-CLI Konfiguration")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Default Instance", cfg.default_instance)
            table.add_row("Current Instance", instance_name)
            table.add_row("Base URL", profile.base_url)
            table.add_row("LMS", profile.lms)
            if profile.client_id:
                table.add_row("Client ID", profile.client_id)
            console.print(table)

    except typer.Exit:
        raise
    except Exception as e:
        raise typer.Exit(code=_handle_exception(e, json_output))


if __name__ == "__main__":
    app()