"""Kommandozeilen-Einstieg der ILIAS-CLI.

Die CLI enthält nur Prompts, Ausgabe und die Abbildung ``IliasError`` ->
Exit-Code. Sämtliche Logik steckt in :mod:`ilias_core`.
"""

from __future__ import annotations

import typer

from ilias_core.client import IliasClient
from ilias_core.config import load_config
from ilias_core.errors import IliasError

from . import output, prompts

app = typer.Typer(
    help="ILIAS-CLI (Phase 1): Login, Status und Logout.",
    no_args_is_help=True,
    add_completion=False,
)


def _fail(exc: IliasError, json_output: bool) -> None:
    if json_output:
        output.print_json(output.error_payload(exc, exc.exit_code))
    else:
        output.print_error(str(exc))
    raise typer.Exit(code=exc.exit_code)


@app.command()
def login(
    json_output: bool = typer.Option(
        False, "--json", help="Maschinenlesbare JSON-Ausgabe."
    ),
    browser: bool = typer.Option(
        False,
        "--browser",
        help="Login in einem sichtbaren Browser (Playwright-Extra erforderlich).",
    ),
    username: str | None = typer.Option(
        None, "--username", help="Benutzername (sonst interaktive Abfrage)."
    ),
) -> None:
    """Meldet sich per OIDC (Keycloak) an und speichert die Session."""

    try:
        client = IliasClient(load_config())
        if browser:
            result = client.login_with_browser()
        else:
            user = username or prompts.ask_username()
            password = prompts.ask_password()
            result = client.login(user, password, prompts.ask_totp)
    except IliasError as exc:
        _fail(exc, json_output)
        return

    if json_output:
        output.print_json(result.to_dict())
    else:
        output.print_login(result)


@app.command()
def status(
    json_output: bool = typer.Option(
        False, "--json", help="Maschinenlesbare JSON-Ausgabe."
    ),
) -> None:
    """Prüft die gespeicherte Session gegen eine geschützte ILIAS-Seite."""

    try:
        result = IliasClient(load_config()).status()
    except IliasError as exc:
        _fail(exc, json_output)
        return

    if json_output:
        output.print_json(result.to_dict())
    else:
        output.print_status(result)


@app.command()
def logout(
    json_output: bool = typer.Option(
        False, "--json", help="Maschinenlesbare JSON-Ausgabe."
    ),
) -> None:
    """Löscht die gespeicherte Session."""

    try:
        removed = IliasClient(load_config()).logout()
    except IliasError as exc:
        _fail(exc, json_output)
        return

    if json_output:
        output.print_json({"ok": True, "session_removed": removed})
    else:
        output.print_logout(removed)


def main() -> None:
    """Entry-Point (``ilias``). Fängt Core-Fehler und setzt den Exit-Code."""

    try:
        app()
    except IliasError as exc:
        output.print_error(str(exc))
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
