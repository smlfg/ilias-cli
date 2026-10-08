"""Dünne CLI-Hülle. Logik liegt in ilias_core."""

from __future__ import annotations

import getpass
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import typer

from ilias_core import moodle as moodle_backend
from ilias_core import tokens
from ilias_core.config import Config, resolve_config
from ilias_core.errors import CliError, NotLoggedInError

app = typer.Typer(help="ILIAS-CLI (Skeleton)", no_args_is_help=True)


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="seconds")


def _ask(prompt: str) -> str:
    sys.stderr.write(prompt)
    sys.stderr.flush()
    return sys.stdin.readline().rstrip("\n").strip()


def _ask_secret(prompt: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(prompt).strip()
    sys.stderr.write(prompt)
    sys.stderr.flush()
    return sys.stdin.readline().rstrip("\n").strip()


def _token_key(cfg: Config) -> str:
    return cfg.instance or cfg.base_url


def _fail(exc: CliError, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps({"ok": False, "error": exc.__class__.__name__, "message": str(exc)}, ensure_ascii=False))
    typer.echo(str(exc), err=True)
    raise typer.Exit(code=exc.exit_code)


def _not_implemented() -> None:
    typer.echo("Nicht implementiert (Skeleton auf main).", err=True)
    raise typer.Exit(code=1)


@app.command()
def login(
    json_output: bool = typer.Option(False, "--json"),
    instance: str | None = typer.Option(None, "--instance"),
) -> None:
    """Login (ILIAS OIDC/Keycloak+TOTP bzw. Moodle Benutzername/Passwort)."""
    try:
        cfg = resolve_config(instance)
    except CliError as exc:
        _fail(exc, json_output)
    if cfg.lms != "moodle":
        _not_implemented()
    username = _ask("Benutzername: ")
    password = _ask_secret("Passwort: ")
    try:
        token = moodle_backend.request_token(cfg.base_url, username, password)
        info = moodle_backend.get_site_info(cfg.base_url, token)
    except CliError as exc:
        _fail(exc, json_output)
    tokens.save_token(_token_key(cfg), token)
    payload = {
        "ok": True,
        "lms": "moodle",
        "instance": cfg.instance,
        "base_url": cfg.base_url,
        "sitename": info.sitename,
        "username": info.username,
        "fullname": info.fullname,
        "timestamp": _now_iso(),
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"Angemeldet bei {info.sitename} als {info.fullname} ({info.username}).")


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json"),
    instance: str | None = typer.Option(None, "--instance"),
) -> None:
    """Session prüfen."""
    try:
        cfg = resolve_config(instance)
    except CliError as exc:
        _fail(exc, json_output)
    if cfg.lms != "moodle":
        _not_implemented()
    token = tokens.load_token(_token_key(cfg))
    if not token:
        exc = NotLoggedInError("Nicht eingeloggt (kein gespeichertes Token).")
        _fail(exc, json_output)
    try:
        info = moodle_backend.get_site_info(cfg.base_url, token)
    except CliError as exc:
        _fail(exc, json_output)
    payload = {
        "ok": True,
        "lms": "moodle",
        "instance": cfg.instance,
        "base_url": cfg.base_url,
        "sitename": info.sitename,
        "username": info.username,
        "fullname": info.fullname,
        "timestamp": _now_iso(),
    }
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"Angemeldet bei {info.sitename} als {info.fullname} ({info.username}).")


@app.command()
def logout(
    json_output: bool = typer.Option(False, "--json"),
    instance: str | None = typer.Option(None, "--instance"),
) -> None:
    """Session löschen."""
    try:
        cfg = resolve_config(instance)
    except CliError as exc:
        _fail(exc, json_output)
    if cfg.lms != "moodle":
        _not_implemented()
    tokens.delete_token(_token_key(cfg))
    payload = {"ok": True, "logged_out": True, "instance": cfg.instance, "timestamp": _now_iso()}
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo("Abgemeldet (Token lokal gelöscht).")
