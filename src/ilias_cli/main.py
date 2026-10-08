"""Dünne CLI-Hülle: ruft nur ilias_core auf, kein eigenes Auth-Wissen."""

from __future__ import annotations

import getpass
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import typer

from ilias_core import config as config_mod
from ilias_core import moodle as moodle_mod
from ilias_core import session as session_mod
from ilias_core.errors import (
    AuthFailedError,
    CliError,
    NetworkError,
    NotLoggedInError,
    ParseError,
    SessionExpiredError,
)

app = typer.Typer(help="ILIAS-CLI (mit Moodle-Backend)", no_args_is_help=True)

BERLIN = ZoneInfo("Europe/Berlin")


def now_berlin_iso() -> str:
    return datetime.now(BERLIN).isoformat()


def _prompt_username() -> str:
    print("Benutzername: ", end="", file=sys.stderr, flush=True)
    try:
        line = sys.stdin.readline()
    except Exception:
        line = ""
    if not line:
        return ""
    return line.rstrip("\r\n").strip()


def _prompt_password() -> str:
    # TTY -> verdeckt; kein TTY (Tests/Pipes) -> Zeile von stdin, Prompt auf stderr.
    try:
        if sys.stdin.isatty():
            try:
                return getpass.getpass("Passwort: ")
            except Exception:
                pass
    except Exception:
        pass
    print("Passwort: ", end="", file=sys.stderr, flush=True)
    try:
        line = sys.stdin.readline()
    except Exception:
        line = ""
    if not line:
        return ""
    return line.rstrip("\r\n")


def _emit_json(payload: dict) -> None:
    # Genau ein JSON-Objekt auf stdout.
    print(json.dumps(payload, ensure_ascii=False))


def _base_payload(resolved) -> dict:
    return {
        "instance": resolved.instance,
        "lms": resolved.lms,
        "base_url": resolved.base_url,
        "checked_at": now_berlin_iso(),
    }


def _require_moodle(resolved, json_output: bool) -> bool:
    if resolved.lms == "moodle":
        return True
    msg = (
        f"Backend '{resolved.lms}' ist hier nicht implementiert "
        f"(Instanz '{resolved.instance or 'default'}'). "
        "Moodle nutzen: --instance hs-mannheim oder lms = \"moodle\" in config.toml."
    )
    print(msg, file=sys.stderr)
    if json_output:
        payload = _base_payload(resolved)
        payload.update({"status": "error", "error": "not_implemented", "message": msg})
        _emit_json(payload)
    raise typer.Exit(code=1)


def _handle_error(exc: CliError, resolved, json_output: bool) -> None:
    # Nie Secrets ausgeben: Nachrichten enthalten keine Passwörter/Tokens.
    print(str(exc), file=sys.stderr)
    if json_output:
        payload = _base_payload(resolved)
        payload.update({"status": _status_for(exc), "error": exc.error_key, "message": str(exc)})
        _emit_json(payload)
    raise typer.Exit(code=exc.exit_code)


def _status_for(exc: CliError) -> str:
    if isinstance(exc, SessionExpiredError):
        return "expired"
    if isinstance(exc, NotLoggedInError):
        return "not_logged_in"
    return "error"


@app.command()
def login(
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbares JSON ausgeben."),
    instance: str | None = typer.Option(None, "--instance", help="Instanzprofil, z. B. hs-mannheim."),
    base_url: str | None = typer.Option(None, "--base-url", help="Basis-URL überschreiben."),
    lms: str | None = typer.Option(None, "--lms", help="Backend: moodle (Standard: ilias)."),
) -> None:
    """Login (Moodle: Benutzername + Passwort, Token via moodle_mobile_app)."""
    resolved = config_mod.resolve(instance_cli=instance, base_url_cli=base_url, lms_cli=lms)
    _require_moodle(resolved, json_output)

    username = _prompt_username()
    password = _prompt_password()
    try:
        if not username or not password:
            raise AuthFailedError("Login fehlgeschlagen (auth_error): Benutzername oder Passwort fehlt.")
        token, info = moodle_mod.login_and_verify(resolved.base_url, username, password)
        # Erst nach erfolgreicher Verifikation speichern.
        session_mod.save_token(resolved.instance, token)
    except CliError as exc:
        _handle_error(exc, resolved, json_output)
    except Exception:
        exc = ParseError("Unerwartete Antwort des Servers.")
        _handle_error(exc, resolved, json_output)
    finally:
        # Passwort sofort aus dem Speicher entlassen (kein Logging!).
        try:
            password = ""  # noqa: F841
        except Exception:
            pass
    # Erfolg melden (nie Token ausgeben).
    if json_output:
        payload = _base_payload(resolved)
        payload.update(
            {
                "status": "ok",
                "username": info.username,
                "fullname": info.fullname,
                "sitename": info.sitename,
                "userid": info.userid,
            }
        )
        _emit_json(payload)
    else:
        print(f"Eingeloggt als {info.fullname} ({info.username}) auf '{info.sitename}'.")
    raise typer.Exit(code=0)


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbares JSON ausgeben."),
    instance: str | None = typer.Option(None, "--instance", help="Instanzprofil, z. B. hs-mannheim."),
    base_url: str | None = typer.Option(None, "--base-url", help="Basis-URL überschreiben."),
    lms: str | None = typer.Option(None, "--lms", help="Backend: moodle (Standard: ilias)."),
) -> None:
    """Session prüfen (Moodle site_info)."""
    resolved = config_mod.resolve(instance_cli=instance, base_url_cli=base_url, lms_cli=lms)
    _require_moodle(resolved, json_output)
    token = session_mod.load_token(resolved.instance)
    if not token:
        exc: CliError = NotLoggedInError("Nicht eingeloggt. Bitte zuerst 'ilias login' ausführen.")
        _handle_error(exc, resolved, json_output)
    try:
        info = moodle_mod.fetch_site_info(resolved.base_url, token or "")
    except CliError as exc2:
        _handle_error(exc2, resolved, json_output)
    except Exception:
        _handle_error(ParseError("Unerwartete Antwort des Servers."), resolved, json_output)
    if json_output:
        payload = _base_payload(resolved)
        payload.update(
            {
                "status": "ok",
                "username": info.username,
                "fullname": info.fullname,
                "sitename": info.sitename,
                "userid": info.userid,
            }
        )
        _emit_json(payload)
    else:
        print(f"Eingeloggt als {info.fullname} ({info.username}) auf '{info.sitename}'.")
    raise typer.Exit(code=0)


@app.command()
def logout(
    json_output: bool = typer.Option(False, "--json", help="Maschinenlesbares JSON ausgeben."),
    instance: str | None = typer.Option(None, "--instance", help="Instanzprofil, z. B. hs-mannheim."),
    base_url: str | None = typer.Option(None, "--base-url", help="Basis-URL überschreiben."),
    lms: str | None = typer.Option(None, "--lms", help="Backend: moodle (Standard: ilias)."),
) -> None:
    """Session lokal löschen (Moodle-Token)."""
    resolved = config_mod.resolve(instance_cli=instance, base_url_cli=base_url, lms_cli=lms)
    # Logout löscht lokal, auch ohne Backend-Unterscheidung; für Nicht-Moodle trotzdem Exit 0.
    try:
        session_mod.delete_token(resolved.instance)
    except Exception:
        pass
    if json_output:
        payload = _base_payload(resolved)
        payload.update({"status": "ok"})
        _emit_json(payload)
    else:
        print("Abgemeldet (lokales Token gelöscht).")
    raise typer.Exit(code=0)
