"""Kommandozeilen-Einstieg der ILIAS-/Moodle-CLI.

Die CLI enthält nur Prompts, Ausgabe und die Abbildung ``IliasError`` ->
Exit-Code. Sämtliche Logik steckt in :mod:`ilias_core`: das Instanz-Register
wählt das Backend (``ilias`` für ``hhn``/``uni-mannheim``, ``moodle`` für
``hs-mannheim``), der Service liefert strukturierte Ergebnisse.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import sys

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
from ilias_core.setup import list_instances_json, run_setup

from . import output, prompts
from rich.console import Console

err_console = Console(stderr=True)

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

    try:
        _, result = _run("login", json_output, instance, debug, op)
    except KeyboardInterrupt:
        if json_output:
            from ilias_core.models import ErrorResult
            output.print_json(ErrorResult(
                command="login",
                error_code="aborted",
                error_type="AbortedError",
                message="Abgebrochen, nichts gespeichert.",
                exit_code=1,
            ).to_json_dict())
        else:
            output.print_error("Abgebrochen, nichts gespeichert.")
        raise typer.Exit(code=1)
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
def setup(
    json_output: bool = JSON_OPTION,
    instance: str | None = typer.Option(
        None,
        "--instance",
        "-i",
        help="Instanz-Profil (eingebaut: hhn, uni-mannheim, hs-mannheim).",
    ),
    username: str | None = typer.Option(
        None, "--username", help="Benutzername (sonst interaktive Abfrage oder Default aus Config)."
    ),
    list_instances: bool = typer.Option(
        False, "--list", help="Alle eingebauten Instanzen anzeigen."
    ),
    filter_text: str | None = typer.Option(
        None, "--filter", help="Filter für die Instanz-Liste (Teilstring in Key, Name, Stadt, LMS)."
    ),
    debug: bool = DEBUG_OPTION,
) -> None:
    """Geführte Erst-Einrichtung: Instanz wählen, Benutzername, Passwort, optional TOTP."""

    if list_instances:
        data = list_instances_json(filter_text)
        if json_output:
            output.print_json(data)
        else:
            for inst in data["instances"]:
                totp = " (2FA)" if inst["requires_totp"] else ""
                print(f"  {inst['key']}: {inst['name']} ({inst['city']}, {inst['lms']}){totp}")
        return

    # Non-interactive path (stdin is not a TTY)
    is_tty = sys.stdin.isatty()
    if not is_tty:
        if debug:
            debuglog.enable()
        try:
            result = run_setup(instance, username, json_output, is_tty)
        except typer.Exit:
            raise
        except KeyboardInterrupt:
            # Ctrl-C: exit 1 with "Abgebrochen, nichts gespeichert."
            if json_output:
                from ilias_core.models import ErrorResult
                output.print_json(ErrorResult(
                    command="setup",
                    error_code="aborted",
                    error_type="AbortedError",
                    message="Abgebrochen, nichts gespeichert.",
                    exit_code=1,
                ).to_json_dict())
            else:
                output.print_error("Abgebrochen, nichts gespeichert.")
            raise typer.Exit(code=1)
        except Exception as exc:  # noqa: BLE001
            from ilias_core.errors import IliasError
            raise _fail("setup", IliasError(str(exc)), json_output, None) from None

        if json_output:
            output.print_json({
                "ok": True,
                "command": "setup",
                "instance": result.instance,
                "lms": "ilias" if result.instance in ("hhn", "uni-mannheim") else "moodle",
                "username": username,
                "verified": True,
                "session_stored": True,
                "config_path": str(result.base_url),
                "timestamp": getattr(result, 'timestamp', ''),
            })
        else:
            print(f"Eingerichtet: {result.instance} als {username}. Neue Eingabe erst nötig, wenn die Session abläuft.")
        return

    # Interactive path (S4)
    if json_output:
        output.print_json({"ok": False, "command": "setup", "error": {"code": "not_implemented", "message": "interactive setup not supported with --json"}})
    else:
        instance_key = _interactive_instance_picker()
        if instance_key is None:
            output.print_error("Abgebrochen, nichts gespeichert.")
            raise typer.Exit(code=1)
        # Re-run setup with selected instance (non-interactive path will handle the rest)
        # For now, we just show the selected instance
        print(f"Ausgewählt: {instance_key}")
        # TODO: Continue with username/password prompts
        output.print_error("Interaktiver Setup nach Instanz-Auswahl noch nicht vollständig implementiert.")
    raise typer.Exit(code=1)


def _interactive_instance_picker() -> str | None:
    """Interaktive Instanz-Auswahl mit Autovervollständigung (prompt_toolkit).

    Returns the selected instance key or None if aborted.
    """
    try:
        from prompt_toolkit import prompt
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.shortcuts import CompleteStyle
    except ImportError:
        # Fallback: numbered list
        return _interactive_instance_picker_fallback()

    from ilias_core.config import BUILTIN_INSTANCES

    class InstanceCompleter(Completer):
        def __init__(self):
            self.instances = list(BUILTIN_INSTANCES.items())

        def get_completions(self, document, complete_event):
            text = document.text.lower()
            for key, profile in self.instances:
                haystack = " ".join([key, profile.name, profile.city, profile.lms]).lower()
                if not text or text in haystack:
                    display = f"{key}: {profile.name} ({profile.city}, {profile.lms})"
                    if profile.requires_totp:
                        display += " (2FA)"
                    yield Completion(key, start_position=-len(document.text), display=display)

    # Print available instances first
    err_console = Console(stderr=True)
    err_console.print("Verfügbare Instanzen (tippen zum Filtern):")
    for key, profile in BUILTIN_INSTANCES.items():
        totp = " (2FA)" if profile.requires_totp else ""
        err_console.print(f"  {key}: {profile.name} ({profile.city}, {profile.lms}){totp}")

    try:
        selected = prompt(
            "Instanz > ",
            completer=InstanceCompleter(),
            complete_style=CompleteStyle.COLUMN,
            err=True,
        ).strip()
    except (KeyboardInterrupt, EOFError):
        return None

    if selected in BUILTIN_INSTANCES:
        return selected

    # If user typed a display name, try to match
    for key, profile in BUILTIN_INSTANCES.items():
        if selected.lower() in profile.name.lower() or selected.lower() == key.lower():
            return key

    err_console.print(f"[bold red]Fehler:[/bold red] Unbekannte Instanz {selected!r}.")
    return None


def _interactive_instance_picker_fallback() -> str | None:
    """Fallback: nummerierte Liste mit Filter-Eingabe."""
    from ilias_core.config import BUILTIN_INSTANCES
    from rich.console import Console

    err_console = Console(stderr=True)

    while True:
        err_console.print("\nVerfügbare Instanzen:")
        for i, (key, profile) in enumerate(BUILTIN_INSTANCES.items(), 1):
            totp = " (2FA)" if profile.requires_totp else ""
            err_console.print(f"  {i}. {key}: {profile.name} ({profile.city}, {profile.lms}){totp}")

        err_console.print("Eingabe: Nummer, Instanz-Key, oder Teilstring zum Filtern (Enter=Abbruch)")
        try:
            choice = sys.stdin.readline()
            if not choice:
                return None
            choice = choice.strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if not choice:
            return None

        # Try as number
        if choice.isdigit():
            idx = int(choice) - 1
            keys = list(BUILTIN_INSTANCES.keys())
            if 0 <= idx < len(keys):
                return keys[idx]

        # Try as key or filter
        choice_lower = choice.lower()
        matches = []
        for key, profile in BUILTIN_INSTANCES.items():
            haystack = " ".join([key, profile.name, profile.city, profile.lms]).lower()
            if choice_lower in haystack:
                matches.append(key)

        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            err_console.print(f"Mehrdeutig: {', '.join(matches)}. Bitte genauer eingeben.")
        else:
            err_console.print(f"Keine Instanz passt auf {choice!r}.")


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
