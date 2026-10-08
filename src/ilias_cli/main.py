"""Kommandozeilen-Einstieg der ILIAS-/Moodle-CLI.

Die CLI enthält nur Prompts, Ausgabe und die Abbildung ``IliasError`` ->
Exit-Code. Sämtliche Logik steckt in :mod:`ilias_core`: das Instanz-Register
wählt das Backend (``ilias`` für ``hhn``/``uni-mannheim``, ``moodle`` für
``hs-mannheim``), der Service liefert strukturierte Ergebnisse.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import typer

from ilias_core import debuglog
from ilias_core.config import BACKEND_MOODLE, BUILTIN_INSTANCES
from ilias_core.errors import IliasError
from ilias_core.models import (
    CourseContentsResult,
    CoursesResult,
    Credentials,
    ErrorResult,
    LoginResult,
    LogoutResult,
    MoodleLoginResult,
    MoodleStatusResult,
    SessionStatus,
)
from ilias_core.secrets import Secret
from ilias_core.service import Service, open_service
from ilias_core.setup import filter_instances

from . import output, prompts

app = typer.Typer(
    help=(
        "ILIAS-/Moodle-CLI: Login, Status, Logout (ILIAS und Moodle), "
        "Kurse und Kursinhalt (Moodle)."
    ),
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
        "und Formularfeld-Namen. Nie Werte, Passwörter, Tokens oder Cookies."
    ),
)


# ---------------------------------------------------------------- Hilfen
def _fail(command: str, exc: IliasError, json_output: bool, service: Service | None) -> typer.Exit:
    """Fehler melden: JSON auf stdout (maschinenlesbar), Text auf stderr."""

    result = ErrorResult(
        command=command,
        error_code=exc.code,
        error_type=type(exc).__name__,
        message=exc.message or str(exc),
        exit_code=exc.exit_code,
        hint=exc.hint,
        instance=service.instance.key if service else None,
        lms=service.instance.lms if service else None,
        candidates=exc.candidates,
    )
    if json_output:
        output.print_json(result.to_json_dict())
    output.print_error(result.message, exc.hint)
    return typer.Exit(code=exc.exit_code)


def _run(
    command: str,
    json_output: bool,
    instance: str | None,
    debug: bool,
    op: Callable[[Service], Any],
) -> tuple[Service, Any]:
    """Instanz auflösen, Operation ausführen, Fehler -> Exit-Code (INTERFACE.md §3).

    Unerwartete Ausnahmen werden nur mit ihrem Typnamen gemeldet: ein Traceback
    könnte Werte lokaler Variablen (Passwort, Token) enthalten (A1).
    """

    if debug:
        debuglog.enable()
    service: Service | None = None
    try:
        service = open_service(instance)
        debuglog.debug(
            "Instanz %s, lms=%s, auth=%s, base_url=%s",
            service.instance.key,
            service.instance.lms,
            service.instance.auth,
            debuglog.redact_url(service.instance.base_url),
        )
        return service, op(service)
    except typer.Exit:
        raise
    except IliasError as exc:
        raise _fail(command, exc, json_output, service) from None
    except KeyboardInterrupt:  # pragma: no cover
        raise typer.Exit(code=130) from None
    except Exception as exc:  # noqa: BLE001 - bewusst: nie einen Traceback ausgeben
        raise _fail(
            command, IliasError(f"Unerwarteter Fehler: {type(exc).__name__}"), json_output, service
        ) from None


def _is_moodle(service: Service) -> bool:
    return service.instance.lms == BACKEND_MOODLE


# ---------------------------------------------------------------- Befehle
@app.command()
def setup(
    json_output: bool = JSON_OPTION,
    instance: str | None = INSTANCE_OPTION,
    username: str | None = typer.Option(
        None, "--username", help="Benutzername (sonst Eingabe/Prompt)."
    ),
    debug: bool = DEBUG_OPTION,
    list_flag: bool = typer.Option(False, "--list", help="Alle eingebauten Instanzen auflisten."),
    filter_text: str | None = typer.Option(
        None, "--filter", help="Instanzen nach Text filtern (Liste/Auswahl)."
    ),
) -> None:
    """Geführte Erst-Einrichtung (Instanz, Benutzername, Passwort, ggf. TOTP)."""

    if debug:
        debuglog.enable()
    if list_flag:
        infos = filter_instances(filter_text or "")
        if json_output:
            output.print_json({"instances": [info.to_dict() for info in infos]})
        else:
            for info in infos:
                totp = "2FA" if info.requires_totp else "kein TOTP"
                console_line = f"{info.key:<14} {info.name} ({info.city}) – {info.lms}, {info.auth}, {totp}, {info.base_url}"
                typer.echo(console_line)
        return
    def op(service: Service) -> Any:
        from ilias_core.errors import NotSupportedError

        raise NotSupportedError("`ilias setup` wird in den nächsten Schritten ergänzt (S2–S4).")

    _run("setup", json_output, instance, debug, op)


@app.command()
def login(
    json_output: bool = JSON_OPTION,
    instance: str | None = INSTANCE_OPTION,
    browser: bool = typer.Option(
        False,
        "--browser",
        help=(
            "Nur ILIAS: Login in einem sichtbaren Browser; nur ILIAS-Cookies werden übernommen. "
            "Vorher: `uv sync --extra browser && uv run playwright install chromium`."
        ),
    ),
    username: str | None = typer.Option(
        None, "--username", help="Benutzername (sonst interaktive Abfrage)."
    ),
    debug: bool = DEBUG_OPTION,
) -> None:
    """Meldet sich an (ILIAS: OIDC/Keycloak oder SAML/Shibboleth; Moodle: Webservice-Token)."""

    def op(service: Service) -> Any:
        backend = service.backend
        if browser:
            if _is_moodle(service):
                raise IliasError(
                    "--browser gibt es nur für ILIAS-Instanzen.",
                    hint="Für Moodle reicht `ilias login --instance hs-mannheim`.",
                )
            return backend.login_with_browser()
        label = getattr(service.instance, "username_label", "Benutzername")
        user = username or prompts.ask_username(label)
        password = prompts.ask_password()
        otp_callback = prompts.ask_totp if backend.uses_totp else None
        return service.login(Credentials(username=user, password=Secret(password)), otp_callback)

    _, result = _run("login", json_output, instance, debug, op)
    if isinstance(result, MoodleLoginResult):
        if json_output:
            output.print_json(result.to_json_dict())
        else:
            output.print_moodle_login(result)
        return
    assert isinstance(result, LoginResult)
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
    """Prüft die gespeicherte Session (Exit 2: keine Session, Exit 3: abgelaufen)."""

    _, result = _run("status", json_output, instance, debug, lambda service: service.status())
    if isinstance(result, MoodleStatusResult):
        if json_output:
            output.print_json(result.to_json_dict())
        else:
            output.print_moodle_status(result)
        return
    assert isinstance(result, SessionStatus)
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
    """Löscht die gespeicherte Session bzw. den Token der Instanz (lokal)."""

    service, result = _run("logout", json_output, instance, debug, lambda s: s.logout())
    assert isinstance(result, LogoutResult)
    if _is_moodle(service):
        if json_output:
            output.print_json(result.to_json_dict())
        else:
            output.print_moodle_logout(result)
        return
    if json_output:
        output.print_json(
            {"ok": True, "session_removed": result.token_removed, "instance": result.instance}
        )
    else:
        output.print_logout(result.token_removed)


@app.command()
def courses(
    json_output: bool = JSON_OPTION,
    instance: str | None = INSTANCE_OPTION,
    debug: bool = DEBUG_OPTION,
) -> None:
    """Eigene Kurse auflisten (ID, Kurzname, Name, Semester). Derzeit nur Moodle."""

    _, result = _run("courses", json_output, instance, debug, lambda service: service.courses())
    assert isinstance(result, CoursesResult)
    if json_output:
        output.print_json(result.to_json_dict())
    else:
        output.print_courses(result)


@app.command()
def ls(
    kurs: str = typer.Argument(..., help="Kurs-ID oder Teilstring von Kurzname/Name."),
    instance: str | None = INSTANCE_OPTION,
    depth: int | None = typer.Option(
        None,
        "--depth",
        "-d",
        help="Baumtiefe: 1=Abschnitte, 2=+Module, 3=+Dateien/erste Ordnerebene, … (Default: alles).",
    ),
    json_output: bool = JSON_OPTION,
    debug: bool = DEBUG_OPTION,
) -> None:
    """Inhalt eines Kurses als Baum (Abschnitte, Module, Dateien). Derzeit nur Moodle."""

    if depth is not None and depth < 1:
        raise typer.BadParameter("--depth muss mindestens 1 sein.")
    _, result = _run("ls", json_output, instance, debug, lambda service: service.ls(kurs, depth))
    assert isinstance(result, CourseContentsResult)
    if json_output:
        output.print_json(result.to_json_dict())
    else:
        output.print_contents(result)


def main() -> None:
    """Entry-Point (``ilias``). Fängt Core-Fehler und setzt den Exit-Code."""

    try:
        app()
    except IliasError as exc:
        output.print_error(str(exc))
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":  # pragma: no cover
    main()
