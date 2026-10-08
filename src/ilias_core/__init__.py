"""Kernbibliothek der ILIAS-CLI.

Enthält Auth, Session, Konfiguration, Modelle und Fehler. CLI und der
spätere MCP-Server sind dünne Hüllen über diesen Funktionen.
"""

from .client import IliasClient
from .config import DEFAULT_BASE_URL, DEFAULT_CLIENT_ID, Config, load_config
from .errors import (
    AuthenticationError,
    BrowserUnavailableError,
    ConfigError,
    IliasError,
    NetworkError,
    NotLoggedInError,
    ParserError,
    SessionExpiredError,
)
from .models import LoginResult, SessionStatus
from .version import __version__

__all__ = [
    "IliasClient",
    "Config",
    "load_config",
    "DEFAULT_BASE_URL",
    "DEFAULT_CLIENT_ID",
    "LoginResult",
    "SessionStatus",
    "IliasError",
    "AuthenticationError",
    "NotLoggedInError",
    "SessionExpiredError",
    "NetworkError",
    "ParserError",
    "BrowserUnavailableError",
    "ConfigError",
    "__version__",
]
