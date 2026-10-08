"""Kommandozeilen-Einstieg der ILIAS-/Moodle-CLI.

Die CLI enthält nur Prompts, Ausgabe und die Abbildung ``IliasError`` ->
Exit-Code. Sämtliche Logik steckt in :mod:`ilias_core`: das Instanz-Register
wählt das Backend (``ilias`` für ``hhn``/``uni-mannheim``, ``moodle`` für
``hs-mannheim``), der Service liefert strukturierte Ergebnisse.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
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
from ilias_core.setup import list_instances

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
def setup(
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbare JSON-Ausgabe."),
    list_inst: bool = typer.Option(
        False, "--list", help="Eingebaute Instanzen auflisten."
    ),
    filter_text: str | None = typer.Option(
        None, "--filter", "-f", help="Filter nach Schlüssel, Anzeigename oder LMS (case-insensitiv)."
    ),
    instance: str | None = INSTANCE_OPTION,
    username: str | None = typer.Option(
        None, "--username", "-u", help="Benutzername (überspringt den Prompt)."
    ),
    debug: bool = DEBUG_OPTION,
) -> None:
    """Geführte Erst-Einrichtung für alle Instanzen (Spec §3)."""

    if list_inst or filter_text is not None:
        # --list [--filter TEXT] [--json] – keine Service-Öffnung nötig
        data = list_instances(filter_text)
        if json_output:
            output.print_json(data)
        else:
            for inst in data["instances"]:
                output.print_error(
                    f"{inst['name']} ({inst['key']}) – {inst['lms']}, "
                    f"Auth: {inst['auth']}, TOTP: {inst['requires_totp']}"
                )
        raise typer.Exit()

    # Nicht-interaktiver Setup-Flow (stdin-Eingaben, Login, Config-Merge)
    def op(service: Service) -> Any:
        # --- Instanz bestimmen ---
        inst_key = service.instance.key
        inst_profile = BUILTIN_INSTANCES.get(inst_key)
        if inst_profile is None:
            raise IliasError(
                f"Unbekannte Instanz {inst_key}.",
                hint=f"Verfügbar: {', '.join(sorted(BUILTIN_INSTANCES))}",
                exit_code=1,
            )

        # --- Benutzername bestimmen ---
        user = username
        if not user:
            # Default aus Config-Datei lesen
            cfg_path = service.config_dir / "config.toml"
            if cfg_path.exists():
                try:
                    with open(cfg_path, "rb") as f:
                        data = tomllib.load(f)
                    inst_data = data.get("instances", {}).get(inst_key, {})
                    user = inst_data.get("username")
                except Exception:
                    pass
            if not user:
                raise IliasError(
                    "Kein Benutzername angegeben und keiner aus der Config übernommen.",
                    hint="`ilias setup --instance <key> --username <name>`",
                    exit_code=1,
                )

        # --- Passwort von stdin lesen ---
        try:
            password_line = sys.stdin.readline()
        except Exception:
            raise IliasError(
                "Fehler beim Lesen des Passworts.",
                exit_code=1,
            )

        if not password_line:
            # EOF vor Passwort -> Abbruch, nichts gespeichert
            raise IliasError(
                "Abgebrochen, nichts gespeichert.",
                hint="`ilias setup --instance <key> --username <name>`",
                exit_code=1,
            )

        password = password_line.rstrip("\r\n")

        # --- TOTP-Code wenn erforderlich ---
        otp_attempts = 0
        max_otp_attempts = 3
        last_otp = None

        if inst_profile.requires_totp:
            # Ersten TOTP-Code von stdin lesen
            try:
                totp_line = sys.stdin.readline()
            except Exception:
                raise IliasError(
                    "Fehler beim Lesen des TOTP-Codes.",
                    exit_code=1,
                )

            if not totp_line:
                # EOF während TOTP-Abfrage -> Abbruch, nichts gespeichert
                raise IliasError(
                    "Abgebrochen, nichts gespeichert.",
                    hint="`ilias setup --instance <key> --username <name>`",
                    exit_code=1,
                )

            last_otp = totp_line.rstrip("\r\n")
            otp_attempts = 1

            # TOTP-Login-Schleife: max 3 Versuche
            while otp_attempts < max_otp_attempts:
                # OTP-Callback erzeugen
                def make_otp_callback(code: str) -> str | None:
                    def callback() -> str | None:
                        return code
                    return callback

                result = service.login(
                    Credentials(username=user, password=Secret(password)), make_otp_callback(last_otp)
                )
                # Wenn erfolgreich, Schleife verlassen
                if result.authenticated:
                    break
                # Wenn fehlgeschlagen, nächsten Code lesen (außer beim letzten Versuch)
                otp_attempts += 1
                if otp_attempts < max_otp_attempts:
                    try:
                        totp_line = sys.stdin.readline()
                    except Exception:
                        raise IliasError(
                            "Fehler beim Lesen des TOTP-Codes.",
                            exit_code=1,
                        )
                    if not totp_line:
                        # EOF während weiterer TOTP-Versuche -> Abbruch
                        raise IliasError(
                            "Abgebrochen, nichts gespeichert.",
                            hint="`ilias setup --instance <key> --username <name>`",
                            exit_code=1,
                        )
                    last_otp = totp_line.rstrip("\r\n")
                else:
                    # Dritter Versuch fehlgeschlagen -> Exit 1
                    raise IliasError(
                        "Maximal number of TOTP attempts reached.",
                        hint="Nach 3 fehlgeschlagenen Code-Versuchen wurde nichts gespeichert.",
                        exit_code=1,
                    )

        # --- Config mergen (atomar) ---
        cfg_path = service.config_dir / "config.toml"
        existing_data: dict[str, Any] = {}

        if cfg_path.exists():
            try:
                with open(cfg_path, "rb") as f:
                    existing_data = tomllib.load(f)
            except Exception:
                pass

        # Neue Konfiguration zusammenbauen:
        # 1. Oben: instance = "<key>"
        # 2. [instances.<key>] section mit username, andere Werte erhalten bleiben
        new_lines: list[str] = [f'instance = "{inst_key}"']

        inst_section = f"instances.{inst_key}"
        if inst_key in existing_data.get("instances", {}):
            # Bestehende Sektion übernehmen, username überschreiben, andere Werte behalten
            new_lines.append(f"[{inst_section}]")
            existing_inst = existing_data["instances"][inst_key]
            for key, val in existing_inst.items():
                if key == "username":
                    new_lines.append(f'username = "{user}"')
                elif isinstance(val, str):
                    new_lines.append(f'{key} = "{val}"')
                elif isinstance(val, bool):
                    new_lines.append(f'{key} = {str(val).lower()}')
                elif isinstance(val, (int, float)):
                    new_lines.append(f'{key} = {val}')
        else:
            # Neue Sektion anlegen
            new_lines.append(f"[{inst_section}]")
            new_lines.append(f'username = "{user}"')

        # Überschreiben atomar via temp file + rename
        tmp_path = cfg_path.with_suffix(".toml.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")
            os.replace(tmp_path, cfg_path)
        except Exception as e:
            raise IliasError(
                f"Konnte Config nicht schreiben: {e}",
                exit_code=1,
            )

        # JSON-Ergebnis ausgeben
        data = {
            "ok": True,
            "command": "setup",
            "instance": inst_key,
            "lms": service.instance.lms,
            "username": user,
            "verified": True,
            "session_stored": True,
            "config_path": str(cfg_path),
            "timestamp": typer.utils.now().isoformat(timespec="seconds"),
        }
        if json_output:
            output.print_json(data)
        else:
            output.print_error(
                f"Eingerichtet: {inst_key} als {user}. Neue Eingabe erst nötig, wenn die Session abläuft.",
                None,
            )

        return data

    try:
        _, result = _run("setup", json_output, instance, debug, op)
        if isinstance(result, dict) and "ok" in result:
            # Bereits von op() ausgegeben, nichts weiteres tun
            pass
    except IliasError as exc:
        if json_output:
            output.print_json(
                {"ok": False, "command": "setup", "error": exc.code, "message": exc.message, "exit_code": exc.exit_code, "hint": exc.hint}
            )
        else:
            output.print_error(exc.message or str(exc), exc.hint)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - bewusst: keinen Traceback ausgeben
        if json_output:
            output.print_json(
                {"ok": False, "command": "setup", "error": type(exc).__name__, "message": str(exc), "exit_code": 1}
            )
        else:
            output.print_error(str(exc), None)


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