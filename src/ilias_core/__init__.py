"""Kernbibliothek: Auth, Session, Config, Modelle, Backends."""

from __future__ import annotations

from .backend import create_backend
from .config import Config, InstanceProfile, get_config_dir
from .exceptions import (
    AuthError,
    ConfigError,
    IliasCliError,
    NetworkError,
    NotLoggedInError,
    ParseError,
    SessionExpiredError,
    moodle_error_to_exception,
)
from .ilias import IliasBackend
from .models import (
    LoginResult,
    LogoutResult,
    MoodleSiteInfo,
    MoodleTokenResponse,
    StatusResult,
)
from .moodle import MoodleBackend
from .session import SessionStore

__version__ = "0.1.0"

__all__ = [
    # Config
    "Config",
    "InstanceProfile",
    "get_config_dir",
    # Models
    "MoodleTokenResponse",
    "MoodleSiteInfo",
    "LoginResult",
    "StatusResult",
    "LogoutResult",
    # Exceptions
    "IliasCliError",
    "AuthError",
    "NotLoggedInError",
    "SessionExpiredError",
    "NetworkError",
    "ParseError",
    "ConfigError",
    "moodle_error_to_exception",
    # Session
    "SessionStore",
    # Backends
    "MoodleBackend",
    "IliasBackend",
    "create_backend",
]