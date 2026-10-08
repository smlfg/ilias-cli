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
    ContentNode,
    Course,
    CourseContentsResult,
    CoursesResult,
    Credentials,
    ErrorResult,
    FileNode,
    FolderNode,
    LoginResult,
    LogoutResult,
    Module,
    Section,
    SiteInfo,
    StatusResult,
    UrlNode,
)
from .secrets import Secret
from .service import Service, open_service, resolve_course, trim_sections
from .session import SessionStore, StoredSession
from .timeutil import semester_from_timestamp, timestamp_to_iso

__all__ = [
    "BUILTIN_INSTANCES",
    "AuthError",
    "ConfigError",
    "ContentNode",
    "CoreError",
    "Course",
    "CourseAmbiguousError",
    "CourseContentsResult",
    "CourseNotFoundError",
    "CoursesResult",
    "Credentials",
    "ErrorResult",
    "FileNode",
    "FolderNode",
    "Instance",
    "LoginResult",
    "LogoutResult",
    "Module",
    "NetworkError",
    "NotLoggedInError",
    "NotSupportedError",
    "ParseError",
    "Secret",
    "Section",
    "Service",
    "SessionExpiredError",
    "SessionStore",
    "SiteInfo",
    "StatusResult",
    "StoredSession",
    "UrlNode",
    "config_dir",
    "config_path",
    "load_instance",
    "open_service",
    "prompt_credentials",
    "prompt_password",
    "prompt_username",
    "resolve_course",
    "semester_from_timestamp",
    "timestamp_to_iso",
    "trim_sections",
    "__version__",
]
