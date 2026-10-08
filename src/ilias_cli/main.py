"""Dünne CLI-Hülle (Skeleton). Siehe INTERFACE.md für den Vertrag.

Moodle-Backend: login via login/token.php + webservice/rest/server.php,
Status-Check, Logout. Session-speicherung per keyring oder 0600-Datei.
"""

from __future__ import annotations

import json
import sys
import os
import getpass
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import typer
import rich.console

from ilias_core import MoodleAuth, MoodleConfig, MoodleSession, MoodleAuthError
from ilias_core.moodle import InvalidLoginError

app = typer.Typer(help="ILIAS-CLI", no_args_is_help=True)

CONFIG_DEFAULTS: MoodleConfig = MoodleConfig(lms="ilias")

CONSOLE = rich.console.Console(stderr=True, force_terminal=True)


def _load_config(config_path: Path | None = None) -> MoodleConfig:
    """Load config from TOML file, fall back to defaults.

    Die Config-Datei hat das Format:
        base_url = "..."
        lms = "moodle"
        instance = "hs-mannheim"
    """
    config = MoodleConfig(lms="ilias", base_url="https://ilias.hs-heilbronn.de")

    paths_to_try = []
    if config_path is not None:
        paths_to_try.append(config_path)
    if ILIAS_CLI_CONFIG_DIR := os.environ.get("ILIAS_CLI_CONFIG_DIR"):
        paths_to_try.append(Path(ILIAS_CLI_CONFIG_DIR) / "config.toml")
    paths_to_try.append(Path.home() / ".config" / "ilias-cli" / "config.toml")

    for path in paths_to_try:
        if path is not None and path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                env = {}
                for line in text.splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        env[key.strip()] = val.strip('"').strip()
                if "base_url" in env:
                    config.base_url = env["base_url"]
                if "lms" in env:
                    config.lms = env["lms"]
                if "instance" in env:
                    config.instance = env["instance"]
            except Exception:
                pass
            break

    return config


def _prompt_username() -> str:
    """Prompt for username (from stdin if no TTY)."""
    try:
        username = typer.prompt("Benutzername", default="")
    except (typer.Exit, KeyboardInterrupt):
        typer.echo("\nAbbruch.", err=True)
        raise typer.Exit(code=1)
    return username.strip()


def _prompt_password() -> str:
    """Prompt for password via hidden TTY or stdin.

    If no controlling TTY, read from stdin (tests write credentials there).
    Otherwise use getpass for hidden input.
    """
    # Try getpass first (hidden TTY)
    try:
        password = getpass.getpass("Passwort")
        return password.strip()
    except (getpass.GetPassphraseError, OSError):
        pass

    # Fallback: read from stdin (tests pipe input: "username\\npassword\\n")
    try:
        lines = sys.stdin.read().strip().splitlines()
        if len(lines) >= 2:
            return lines[1].strip()
    except Exception:
        pass

    # Last resort: ask again (may echo)
    password = typer.prompt("Passwort", hide_input=True)
    return password.strip()


def _exit_code_for_error(error: Exception) -> int:
    """Map Moodle auth errors to exit codes per INTERFACE.md."""

    from httpx import HTTPStatusError

    if isinstance(error, InvalidLoginError):
        # Wrong password/credentials -> exit 1 (or 2, both accepted per INTERFACE.md §3)
        return 1

    if isinstance(error, MoodleAuthError):
        # Network / 5xx -> exit 4
        # Unexpected response -> exit 5
        # Check if it's a network/connectivity issue
        msg = str(error).lower()
        if any(
            kw in msg
            for kw in ["network", "connection", "refused", "failed to connect", "http 5", "500", "502", "503", "504"]
        ):
            return 4
        return 5

    # Default
    return 1


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@app.command()
def login(
    instance: str = typer.Option(
        "",
        "--instance",
        help="LMS-Instanzname (z. B. hs-mannheim). Überschreibt config.toml.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Moodle login via Moodle Mobile web service (only if lms=moodle).

    POST {base}/login/token.php mit username, password, service=moodle_mobile_app.
    Erfolgreich: Token speichern und fullname/username + sitename anzeigen.
    Fehler: Klartext-Fehlermeldung und Exit-Code.
    """
    config = _load_config()

    # Only run Moodle flow if lms=moodle; otherwise not-implemented
    if config.lms != "moodle":
        typer.echo("Login nur mit lms=moodle konfiguriert.", err=True)
        raise typer.Exit(code=1)

    # Select instance: CLI --instance > config instance > default
    instance_name = instance or config.instance or "hs-mannheim"
    if not config.base_url:
        config.base_url = "https://moodle.hs-mannheim.de"

    # Override base_url for this instance if configured
    instance_base = config.base_url

    auth = MoodleAuth(config)

    try:
        username = _prompt_username()
        password = _prompt_password()

        session = auth.login(username, password, base_url=instance_base)

        # Store token (keyring or 0600 file)
        auth.store_token(session)

        if json_output:
            output = {
                "status": "ok",
                "fullname": session.fullname,
                "username": session.username,
                "sitename": session.sitename,
                "instance": instance_name,
            }
            typer.echo(json.dumps(output, ensure_ascii=False))
        else:
            CONSOLE.print(f"Erfolgreich eingeloggt bei {session.sitename}")
            CONSOLE.print(f"Vollständiger Name: {session.fullname}")
            CONSOLE.print(f"Benutzername: {session.username}")

    except InvalidLoginError as exc:
        typer.echo(f"Login fehlgeschlagen: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for_error(exc))
    except MoodleAuthError as exc:
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for_error(exc))
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Unexpected error: {exc}", err=True)
        raise typer.Exit(code=4)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.command()
def status(
    instance: str = typer.Option(
        "",
        "--instance",
        help="LMS-Instanzname (z. B. hs-mannheim).",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Session prüfen.

    Prüft mit stored Token + site_info.
    Invalid token -> Exit 3. No stored token -> Exit 2.
    """
    config = _load_config()

    instance_name = instance or config.instance or "hs-mannheim"
    if not config.base_url:
        config.base_url = "https://moodle.hs-mannheim.de"

    auth = MoodleAuth(config)

    try:
        # Try to load stored token
        session = auth.load_stored_token(instance_name)

        if session is None or not session.token:
            # No stored token
            if json_output:
                typer.echo(json.dumps({"status": "not_logged_in"}))
            else:
                CONSOLE.print("Nicht eingeloggt (keine gespeicherte Session).")
            raise typer.Exit(code=2)

        # Verify session with site info
        verified = auth.check_status(session)

        if json_output:
            output = {
                "status": "ok",
                "fullname": verified.fullname,
                "username": verified.username,
                "sitename": verified.sitename,
                "userid": verified.userid,
                "instance": instance_name,
            }
            typer.echo(json.dumps(output, ensure_ascii=False))
        else:
            CONSOLE.print(f"Eingeloggt bei {verified.sitename}")
            CONSOLE.print(f"Vollständiger Name: {verified.fullname}")
            CONSOLE.print(f"Benutzername: {verified.username} (User ID: {verified.userid})")

    except InvalidLoginError as exc:
        typer.echo(f"Session invalid: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for_error(exc))
    except MoodleAuthError as exc:
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(code=_exit_code_for_error(exc))
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Unexpected error: {exc}", err=True)
        raise typer.Exit(code=4)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@app.command()
def logout(
    instance: str = typer.Option(
        "",
        "--instance",
        help="LMS-Instanzname (z. B. hs-mannheim).",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Session löschen.

    Löscht Session aus Keyring **UND** Datei.
    Exit 0 auch wenn nichts gespeichert war.
    """
    config = _load_config()

    inst = instance or config.instance or "hs-mannheim"

    auth = MoodleAuth(config)
    auth.logout(inst)

    if json_output:
        typer.echo(json.dumps({"status": "ok", "instance": inst}))
    else:
        CONSOLE.print(f"Session für Instanz '{inst}' wurde gelöscht.")


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def _default_callback(
    ctx: typer.Context,
    instance: str = typer.Option(
        "",
        "--instance",
        help="LMS-Instanzname (z. B. hs-mannheim).",
    ),
) -> None:
    """Standard callback when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        typer.echo("Verwende: ilias login | ilias status | ilius logout")
        raise typer.Exit(code=0)