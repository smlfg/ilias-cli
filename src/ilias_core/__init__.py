"""Kernbibliothek: Config, Auth, Session, Backends, Modelle, Fehler.

Die CLI (`ilias_cli`) ist nur eine dünne Hülle: sie liest keine Logik, sie
formatiert nur die strukturierten Rückgabewerte dieser Bibliothek
(ANFORDERUNGEN.md §1, INTERFACE.md §1).
"""

from __future__ import annotations

__version__ = "0.1.0"

from .auth import prompt_credentials, prompt_password, prompt_username
from .config import BUILTIN_INSTANCES, Instance, config_dir, config_path, load_instance
from .errors import (
    AuthError,
    ConfigError,
    CoreError,
    NetworkError,
    NotLoggedInError,
    NotSupportedError,
    ParseError,
    SessionExpiredError,
)
from .models import (
    Credentials,
    ErrorResult,
    LoginResult,
    LogoutResult,
    SiteInfo,
    StatusResult,
)
from .secrets import Secret
from .service import Service, open_service
from .session import SessionStore, StoredSession

__all__ = [
    "BUILTIN_INSTANCES",
    "AuthError",
    "ConfigError",
    "CoreError",
    "Credentials",
    "ErrorResult",
    "Instance",
    "LoginResult",
    "LogoutResult",
    "NetworkError",
    "NotLoggedInError",
    "NotSupportedError",
    "ParseError",
    "Secret",
    "Service",
    "SessionExpiredError",
    "SessionStore",
    "SiteInfo",
    "StatusResult",
    "StoredSession",
    "config_dir",
    "config_path",
    "load_instance",
    "open_service",
    "prompt_credentials",
    "prompt_password",
    "prompt_username",
    "__version__",
]
