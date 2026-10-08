"""Kernbibliothek: Config, Auth, Session, Backends, Modelle, Fehler.

Die CLI (`ilias_cli`) ist nur eine dünne Hülle: sie liest keine Logik, sie
formatiert nur die strukturierten Rückgabewerte dieser Bibliothek
(ANFORDERUNGEN.md §1, INTERFACE.md §1).
"""

from __future__ import annotations

__version__ = "0.1.0"

from .auth import prompt_credentials, prompt_password, prompt_username
from .config import BUILTIN_INSTANCES, Instance, config_dir, config_path, load_instance
from .courses import apply_depth, course_sort_key, resolve_course, sort_courses
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
    CourseListResult,
    CourseRef,
    Credentials,
    ErrorResult,
    FileNode,
    FolderNode,
    LoginResult,
    LogoutResult,
    ModuleNode,
    SectionNode,
    SiteInfo,
    StatusResult,
    UrlNode,
)
from .secrets import Secret
from .service import Service, open_service
from .session import SessionStore, StoredSession
from .text import plain_text, strip_html
from .timeutil import iso_or_none, now_iso, semester_from_timestamp

__all__ = [
    "BUILTIN_INSTANCES",
    "AuthError",
    "ConfigError",
    "ContentNode",
    "CoreError",
    "Course",
    "CourseAmbiguousError",
    "CourseContentsResult",
    "CourseListResult",
    "CourseNotFoundError",
    "CourseRef",
    "Credentials",
    "ErrorResult",
    "FileNode",
    "FolderNode",
    "Instance",
    "LoginResult",
    "LogoutResult",
    "ModuleNode",
    "NetworkError",
    "NotLoggedInError",
    "NotSupportedError",
    "ParseError",
    "Secret",
    "SectionNode",
    "Service",
    "SessionExpiredError",
    "SessionStore",
    "SiteInfo",
    "StatusResult",
    "StoredSession",
    "UrlNode",
    "apply_depth",
    "config_dir",
    "config_path",
    "course_sort_key",
    "iso_or_none",
    "load_instance",
    "now_iso",
    "open_service",
    "plain_text",
    "prompt_credentials",
    "prompt_password",
    "prompt_username",
    "resolve_course",
    "semester_from_timestamp",
    "sort_courses",
    "strip_html",
    "__version__",
]
