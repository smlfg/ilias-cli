"""Dünne CLI-Hülle (typer). Die Logik liegt in ``ilias_core``.

Unterstützt ILIAS (Platzhalter) und Moodle. Beispiel:
    ilias login  --instance hs-mannheim [--json]
    ilias status --instance hs-mannheim [--json]
    ilias logout --instance hs-mannheim [--json]
"""

from __future__ import annotations

from typing import Optional

import typer

from ilias_core.auth import AuthService
from ilias_core.config import load_config
from ilias_core.errors import IliasCliError

app = typer.Typer(help="ILIAS-/Moodle-CLI", no_args_is_help=True)

_INSTANCE_HELP = "Instanz-Profil, z. B. hs-mannheim (Moodle) oder hhn (ILIAS)."
_BASE_URL_HELP = "Basis-URL der Instanz (überschreibt config.toml und Profil)."


def _emit_error(exc: IliasCliError, json_output: bool) -> None:
    if json_output:
        typer.echo(
            _json(
                {
                    "error": str(exc),
                    "errorcode": exc.errorcode,
                    "exit_code": exc.exit_code,
                }
            )
        )
    else:
        typer.echo(f"Fehler: {exc}", err=True)
    raise typer.Exit(exc.exit_code)


def _json(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False)


def _service(instance: Optional[str], base_url: Optional[str]) -> AuthService:
    config = load_config(instance=instance, base_url=base_url)
    if not config.is_moodle:
        raise IliasCliError(
            "Das ILIAS-Backend ist noch nicht implementiert. "
            "Für Moodle: --instance hs-mannheim."
        )
    return AuthService(config)


@app.command()
def login(
    instance: Optional[str] = typer.Option(None, "--instance", "-i", help=_INSTANCE_HELP),
    base_url: Optional[str] = typer.Option(None, "--base-url", help=_BASE_URL_HELP),
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbare Ausgabe."),
) -> None:
    """Anmelden und Token speichern (Passwort verdeckt)."""
    try:
        service = _service(instance, base_url)
    except IliasCliError as exc:
        _emit_error(exc, json_output)

    username = typer.prompt("Benutzername", err=True)
    password = typer.prompt("Passwort", hide_input=True, err=True)

    try:
        result = service.login(username, password)
    except IliasCliError as exc:
        _emit_error(exc, json_output)
        return

    if json_output:
        typer.echo(_json(result.to_dict()))
    else:
        typer.echo(
            f"Angemeldet als {result.fullname} ({result.username}) "
            f"auf {result.sitename} [{result.instance}]."
        )


@app.command()
def status(
    instance: Optional[str] = typer.Option(None, "--instance", "-i", help=_INSTANCE_HELP),
    base_url: Optional[str] = typer.Option(None, "--base-url", help=_BASE_URL_HELP),
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbare Ausgabe."),
) -> None:
    """Gespeicherte Sitzung prüfen."""
    try:
        service = _service(instance, base_url)
        result = service.status()
    except IliasCliError as exc:
        _emit_error(exc, json_output)
        return

    if json_output:
        typer.echo(_json(result.to_dict()))
    else:
        typer.echo(
            f"Eingeloggt als {result.fullname} ({result.username}) "
            f"auf {result.sitename} [{result.instance}]."
        )


@app.command()
def logout(
    instance: Optional[str] = typer.Option(None, "--instance", "-i", help=_INSTANCE_HELP),
    base_url: Optional[str] = typer.Option(None, "--base-url", help=_BASE_URL_HELP),
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbare Ausgabe."),
) -> None:
    """Gespeicherten Token lokal löschen."""
    try:
        service = _service(instance, base_url)
        result = service.logout()
    except IliasCliError as exc:
        _emit_error(exc, json_output)
        return

    if json_output:
        typer.echo(_json(result.to_dict()))
    else:
        typer.echo(
            "Abgemeldet." if result.removed else "Keine gespeicherte Sitzung vorhanden."
        )


if __name__ == "__main__":
    app()
