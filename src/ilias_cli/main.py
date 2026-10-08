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
    if sys.stdin.isatty():
        return typer.prompt("Benutzername", prompt_suffix=": ")
    # Non-TTY: read one line from stdin
    line = sys.stdin.readline()
    if not line:
        return ""
    return line.rstrip("\n")


def _prompt_password() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("Passwort: ", stream=sys.stderr)
    # Non-TTY: read one line from stdin
    line = sys.stdin.readline()
    if not line:
        return ""
    return line.rstrip("\n")


def _prompt_totp() -> str:
    if sys.stdin.isatty():
        return typer.prompt("TOTP-Code", prompt_suffix=": ", hide_input=True)
    # Non-TTY: read one line from stdin
    line = sys.stdin.readline()
    if not line:
        return ""
    return line.rstrip("\n")


def _handle_exception(e: Exception, json_output: bool) -> int:
    """Behandelt Exceptions und gibt passenden Exit-Code zurück."""
    if isinstance(e, (AuthError, NotLoggedInError, SessionExpiredError, NetworkError, ParseError)):
        # JSON immer auf stdout ausgeben
        import json

        error_data = {"success": False, "error": str(e), "exit_code": e.exit_code}
        if hasattr(e, "errorcode") and e.errorcode:
            error_data["errorcode"] = e.errorcode
        print(json.dumps(error_data, ensure_ascii=False))
        if not json_output:
            console.print(f"[red]Fehler:[/red] {e}")
        return e.exit_code

    # Unerwarteter Fehler
    import json

    print(json.dumps({"success": False, "error": "Interner Fehler", "exit_code": 1}, ensure_ascii=False))
    if not json_output:
        console.print(f"[red]Interner Fehler:[/red] {e}")
    return 1


@app.command()
def login(
    instance: Annotated[str | None, typer.Option("--instance", "-i", help="Instanz-Profil (z. B. hs-mannheim)")] = None,
    config_dir: Annotated[str | None, typer.Option("--config-dir", help="Konfigurationsverzeichnis")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Base-URL überschreiben")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON-Ausgabe (nur JSON, keine Prompts auf stdout)")] = False,
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
                totp = _prompt_totp()
                result = backend.login(username, password, totp=totp)

        # JSON immer auf stdout ausgeben
        _print_result_json(result)
        # Human output nur ohne --json auf stderr
        if not json_output:
            _print_result_human(result)

        exit_code = result.exit_code
    except typer.Exit:
        raise
    except Exception as e:
        exit_code = _handle_exception(e, json_output)
    
    raise typer.Exit(code=exit_code)


@app.command()
def status(
    instance: Annotated[str | None, typer.Option("--instance", "-i", help="Instanz-Profil (z. B. hs-mannheim)")] = None,
    config_dir: Annotated[str | None, typer.Option("--config-dir", help="Konfigurationsverzeichnis")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Base-URL überschreiben")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON-Ausgabe (nur JSON auf stdout)")] = False,
) -> None:
    """Prüft ob eine gültige Session/Token existiert."""
    try:
        cfg, profile = _load_config(instance, config_dir)

        if base_url:
            profile.base_url = base_url.rstrip("/")

        with create_backend(profile, config_dir) as backend:
            result = backend.status()
            result.last_checked = datetime.now()

        # JSON immer auf stdout ausgeben
        _print_result_json(result)
        # Human output nur ohne --json auf stderr
        if not json_output:
            _print_result_human(result)

        exit_code = result.exit_code
    except typer.Exit:
        raise
    except Exception as e:
        exit_code = _handle_exception(e, json_output)
    
    raise typer.Exit(code=exit_code)


@app.command()
def logout(
    instance: Annotated[str | None, typer.Option("--instance", "-i", help="Instanz-Profil (z. B. hs-mannheim)")] = None,
    config_dir: Annotated[str | None, typer.Option("--config-dir", help="Konfigurationsverzeichnis")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="Base-URL überschreiben")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="JSON-Ausgabe (nur JSON auf stdout)")] = False,
) -> None:
    """Löscht lokale Session/Token."""
    try:
        cfg, profile = _load_config(instance, config_dir)

        if base_url:
            profile.base_url = base_url.rstrip("/")

        with create_backend(profile, config_dir) as backend:
            result = backend.logout()

        # JSON immer auf stdout ausgeben
        _print_result_json(result)
        # Human output nur ohne --json auf stderr
        if not json_output:
            _print_result_human(result)

        exit_code = result.exit_code
    except typer.Exit:
        raise
    except Exception as e:
        exit_code = _handle_exception(e, json_output)
    
    raise typer.Exit(code=exit_code)


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

        exit_code = 0
    except typer.Exit:
        raise
    except Exception as e:
        exit_code = _handle_exception(e, json_output)
    
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()