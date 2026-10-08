"""ILIAS Core Library - Authentication, Session, and Data Models."""

from ilias_core.auth import (
    AuthClient,
    check_session_status,
    is_login_error_page,
    is_totp_page,
    parse_login_form,
    parse_totp_form,
)
from ilias_core.config import Config, ensure_config_dir, get_config_path, load_config, save_config
from ilias_core.errors import (
    BrowserNotAvailableError,
    ILIASError,
    InvalidCredentialsError,
    InvalidTOTPError,
    NetworkError,
    NotLoggedInError,
    ParserError,
    SessionExpiredError,
)
from ilias_core.models import LoginResult, LogoutResult, SessionCookies, SessionStatus
from ilias_core.session import (
    FileSessionStore,
    KeyringSessionStore,
    SessionStore,
    create_session_store,
)

__all__ = [
    "Config",
    "load_config",
    "save_config",
    "ensure_config_dir",
    "get_config_path",
    "ILIASError",
    "NetworkError",
    "ParserError",
    "NotLoggedInError",
    "SessionExpiredError",
    "InvalidCredentialsError",
    "InvalidTOTPError",
    "BrowserNotAvailableError",
    "LoginResult",
    "SessionStatus",
    "SessionCookies",
    "LogoutResult",
    "SessionStore",
    "FileSessionStore",
    "KeyringSessionStore",
    "create_session_store",
    "AuthClient",
    "parse_login_form",
    "parse_totp_form",
    "is_login_error_page",
    "is_totp_page",
    "check_session_status",
]