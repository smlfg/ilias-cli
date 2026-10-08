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
    CourseAmbiguousError,
    CourseNotFoundError,
    NetworkError,
    NotLoggedInError,
    NotSupportedError,
    ParseError,
    SessionExpiredError,
)
from .models import (
    Course,
    CoursesResult,
    Credentials,
    ErrorResult,
    LoginResult,
    LogoutResult,
    LsResult,
    SiteInfo,
    StatusResult,
    semester_for_startdate,
)
from .secrets import Secret
from .service import Service, open_service
from .session import SessionStore, StoredSession

__all__ = [
    "BUILTIN_INSTANCES",
    "AuthError",
    "ConfigError",
    "CourseAmbiguousError",
    "CourseNotFoundError",
    "CoreError",
    "Course",
    "CoursesResult",
    "Credentials",
    "ErrorResult",
    "Instance",
    "LoginResult",
    "LogoutResult",
    "LsResult",
    "NetworkError",
    "NotLoggedInError",
    "NotSupportedError",
    "ParseError",
    "Secret",
    "Service",
    "SessionExpiredError",
    "SessionStore",
    "SiteInfo",
    "semester_for_startdate",
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
