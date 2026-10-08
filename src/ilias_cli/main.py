"""Dünne CLI-Hülle: Typer-Kommandos, JSON-Ausgabe, Exit-Codes (INTERFACE.md).

Keine Logik hier: Auflösen der Instanz, Login/Status/Logout und die Fehler->Exit-Code-
Abbildung kommen aus `ilias_core`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ilias_core import (
    CoreError,
    ErrorResult,
    Service,
    __version__,
    open_service,
)
from ilias_core.models import (
    LsFile,
    LsFolder,
    LsResult,
    LsUrl,
    LoginResult,
    LogoutResult,
    StatusResult,
    Course,
)
from ilias_core.service import Service as ServiceCls

app = typer.Typer(
    help="ilias-cli – Login/Status/Logout für ILIAS- und Moodle-Instanzen (Hochschulen).",
    no_args_is_help=True,
)

err_console = Console(stderr=True, highlight=False, soft_wrap=True)
out_console = Console(highlight=False, soft_wrap=True)

def _instance_option() -> Any:
    return typer.Option(
        None,
        "--instance",
        "-i",
        help="Instanz-Schlüssel aus config.toml (z. B. hhn, hs-mannheim).",
    )


def _json_option() -> Any:
    return typer.Option(
        False, "--json", help="Maschinenlesbare Ausgabe (ein JSON-Objekt auf stdout)."
    )


# ---------------------------------------------------------------- Hilfen
def _dump(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _fail(
    command: str,
    exc: CoreError,
    json_output: bool,
    service: Service | None = None,
) -> typer.Exit:
    """Fehler melden: JSON auf stdout (maschinenlesbar), Text auf stderr."""
    result = ErrorResult(
        command=command,
        error_code=exc.code,
        message=exc.message,
        exit_code=exc.exit_code,
        hint=exc.hint,
        instance=service.instance.key if service else None,
        lms=service.instance.lms if service else None,
    )
    if json_output:
        _dump(result.to_json_dict())
    err_console.print(f"[bold red]Fehler:[/bold red] {escape(exc.message)}")
    if exc.hint:
        err_console.print(f"[dim]Hinweis:[/dim] {escape(exc.hint)}")
    err_console.print(f"[dim]Exit-Code {exc.exit_code} (siehe INTERFACE.md)[/dim]")
    return typer.Exit(code=exc.exit_code)


def _version_callback(value: bool) -> None:
    if value:
        out_console.print(f"ilias-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Version anzeigen."
    ),
) -> None:
    """ilias-cli: Anmeldung an Hochschul-Lernplattformen (ILIAS, Moodle)."""


def _session_table(result: LoginResult | StatusResult) -> Table:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_row("Instanz", escape(f"{result.instance} ({result.lms})"))
    table.add_row("Server", escape(result.base_url))
    table.add_row("Angemeldet als", escape(result.username))
    if result.fullname:
        table.add_row("Name", escape(result.fullname))
    if result.sitename:
        table.add_row("Plattform", escape(result.sitename))
    if result.userid is not None:
        table.add_row("User-ID", str(result.userid))
    table.add_row("Token", "gespeichert (nicht ausgegeben)")
    table.add_row("Zeitpunkt", result.timestamp)
    return table


# ---------------------------------------------------------------- Befehle
def _run(command: str, json_output: bool, instance: str | None, op: Callable[[Service], Any]) -> Any:
    """Eine Core-Operation ausführen und Fehler -> Exit-Code (INTERFACE.md §3).

    Unerwartete Ausnahmen werden bewusst nur als Typname gemeldet: ein Traceback
    könnte Werte lokaler Variablen enthalten (A1).
    """
    service: Service | None = None
    try:
        service = open_service(instance)
        return op(service)
    except CoreError as exc:
        raise _fail(command, exc, json_output, service) from None
    except KeyboardInterrupt:  # pragma: no cover
        raise typer.Exit(code=130) from None
    except Exception as exc:
        raise _fail(
            command,
            CoreError(f"Unerwarteter Fehler: {type(exc).__name__}"),
            json_output,
            service,
        ) from None


@app.command()
def login(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Anmelden und Session speichern (fragt Benutzername und Passwort verdeckt ab)."""
    result: LoginResult = _run("login", json_output, instance, lambda service: service.login())
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print("[green]Anmeldung erfolgreich[/green]")
    out_console.print(_session_table(result))


@app.command()
def status(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Gespeicherte Session prüfen (Exit 2: keine Session, Exit 3: abgelaufen)."""
    result: StatusResult = _run("status", json_output, instance, lambda service: service.status())
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print(f"[green]Session gültig[/green] ({result.instance}, {result.lms})")
    out_console.print(_session_table(result))


@app.command()
def logout(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Gespeicherte Session lokal löschen (Keyring und Datei)."""
    result: LogoutResult = _run("logout", json_output, instance, lambda service: service.logout())
    if json_output:
        _dump(result.to_json_dict())
        return
    if result.token_removed:
        out_console.print(f"Session für {result.instance} ({result.lms}) gelöscht.")
    else:
        out_console.print(f"Keine gespeicherte Session für {result.instance} ({result.lms}) - nichts zu tun.")
    out_console.print(f"[dim]{result.timestamp}[/dim]")


def main_entrypoint() -> None:  # pragma: no cover - Einstieg über Konsolen-Skript
    app()


if __name__ == "__main__":  # pragma: no cover
    main_entrypoint()
