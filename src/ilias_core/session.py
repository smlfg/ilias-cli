from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import httpx
import keyring

from . import auth
from .config import config_dir
from .errors import NetworkError, ParserError, SessionExpiredError
from .keycloak_parser import looks_like_login_page
from .models import SessionData, SessionStatus

SERVICE = "ilias-cli"
ENTRY = "session"


def _file_path() -> Path:
    return config_dir() / "session.json"


def save_session(session: SessionData) -> str:
    payload = session.model_dump_json()
    try:
        keyring.set_password(SERVICE, ENTRY, payload)
        _remove_file_fallback()
        return "keyring"
    except Exception:
        path = _file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        path.write_text(payload, encoding="utf-8")
        os.chmod(path, 0o600)
        return "file"


def load_session() -> SessionData | None:
    try:
        raw = keyring.get_password(SERVICE, ENTRY)
    except Exception:
        raw = None
    if raw:
        try:
            return SessionData.model_validate_json(raw)
        except ValueError:
            return None
    path = _file_path()
    if path.exists():
        try:
            return SessionData.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def delete_session() -> None:
    try:
        keyring.delete_password(SERVICE, ENTRY)
    except Exception:
        pass
    _remove_file_fallback()


def _remove_file_fallback() -> None:
    try:
        path = _file_path()
        if path.exists():
            path.unlink()
    except OSError:
        pass


def check_session(session: SessionData, *, client: httpx.Client | None = None) -> SessionStatus:
    own_client = client is None
    c = client or auth.make_client(cookies=session.cookies)
    try:
        try:
            resp = c.get(f"{session.base_url}/ilias.php?baseClass=ilDashboardGUI")
        except httpx.HTTPError as exc:
            raise NetworkError(f"Netzwerk-/Serverfehler: {type(exc).__name__}") from exc
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location", "")
            if "login.php" in location or "openidconnect" in location:
                raise SessionExpiredError("Session abgelaufen (Redirect zu login.php)")
            raise ParserError(f"Unerwartete Weiterleitung ({location})")
        if resp.status_code >= 400:
            raise NetworkError(f"Serverfehler (HTTP {resp.status_code})")
        if looks_like_login_page(resp.text):
            raise SessionExpiredError("Session abgelaufen (Login-Formular im HTML)")
        if 'name="username"' in resp.text and 'name="password"' in resp.text and "ilDashboard" not in resp.text:
            raise SessionExpiredError("Session abgelaufen (Login-Formular im HTML)")
        return SessionStatus(logged_in=True, base_url=session.base_url)
    finally:
        if own_client:
            c.close()
