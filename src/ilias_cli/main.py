"""Kommandozeilen-Einstieg der ILIAS-CLI.

Die CLI enthält nur Prompts, Ausgabe und die Abbildung ``IliasError`` ->
Exit-Code. Sämtliche Logik steckt in :mod:`ilias_core`.
"""

from __future__ import annotations

import typer

from ilias_core import debuglog
from ilias_core.client import IliasClient
from ilias_core.config import BUILTIN_INSTANCES, load_config
from ilias_core.errors import IliasError

from . import output, prompts

app = typer.Typer(
    help="ILIAS-CLI (Phase 1): Login, Status und Logout.",
    no_args_is_help=True,
    add_completion=False,
)

JSON_OPTION = typer.Option(False, "--json", help="Maschinenlesbare JSON-Ausgabe.")
INSTANCE_OPTION = typer.Option(
    None,
    "--instance",
    "-i",
    help=(
        "Instanz-Profil (eingebaut: "
        + ", ".join(sorted(BUILTIN_INSTANCES))
        + "; sonst `instance` aus config.toml, Default hhn)."
    ),
)
DEBUG_OPTION = typer.Option(
    False,
    "--debug",
    help=(
        "Sicheres Debug-Log auf stderr: nur URLs (ohne Query-Werte), Statuscodes "
        "und Formularfeld-Namen. Nie Werte, Passwörter oder Cookies."
    ),
)


def _fail(exc: IliasError, json_output: bool) -> None:
    if json_output:
        output.print_json(output.error_payload(exc, exc.exit_code))
    else:
        output.print_error(str(exc))
    raise typer.Exit(code=exc.exit_code)


def _client(instance: str | None, debug: bool) -> IliasClient:
    if debug:
        debuglog.enable()
    config = load_config(instance=instance)
    debuglog.debug(
        "Instanz %s, auth=%s, base_url=%s",
        config.instance,
        config.auth,
        debuglog.redact_url(config.base_url),
    )
    return IliasClient(config)


@app.command()
def login(
    json_output: bool = JSON_OPTION,
    instance: str | None = INSTANCE_OPTION,
    browser: bool = typer.Option(
        False,
        "--browser",
        help=(
            "Login in einem sichtbaren Browser; nur ILIAS-Cookies werden übernommen. "
            "Vorher: `uv sync --extra browser && uv run playwright install chromium`."
        ),
    ),
    username: str | None = typer.Option(
        None, "--username", help="Benutzername (sonst interaktive Abfrage)."
    ),
    debug: bool = DEBUG_OPTION,
) -> None:
    """Meldet sich an (OIDC/Keycloak oder SAML/Shibboleth) und speichert die Session."""

    try:
        client = _client(instance, debug)
        if browser:
            result = client.login_with_browser()
        else:
            user = username or prompts.ask_username(client.config.username_label)
            password = prompts.ask_password()
            otp_callback = prompts.ask_totp if client.uses_totp else None
            result = client.login(user, password, otp_callback)
    except IliasError as exc:
        _fail(exc, json_output)
        return

    if json_output:
        output.print_json(result.to_dict())
    else:
        output.print_login(result)


@app.command()
def status(
    json_output: bool = JSON_OPTION,
    instance: str | None = INSTANCE_OPTION,
    debug: bool = DEBUG_OPTION,
) -> None:
    """Prüft die gespeicherte Session gegen das ILIAS-Dashboard."""

    try:
        result = _client(instance, debug).status()
    except IliasError as exc:
        _fail(exc, json_output)
        return

    if json_output:
        output.print_json(result.to_dict())
    else:
        output.print_status(result)


@app.command()
def logout(
    json_output: bool = JSON_OPTION,
    instance: str | None = INSTANCE_OPTION,
    debug: bool = DEBUG_OPTION,
) -> None:
    """Löscht die gespeicherte Session der Instanz."""

    try:
        client = _client(instance, debug)
        removed = client.logout()
    except IliasError as exc:
        _fail(exc, json_output)
        return

    if json_output:
        output.print_json(
            {"ok": True, "session_removed": removed, "instance": client.config.instance}
        )
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
