"""Backend-Factory für pluggable LMS (moodle, ilias)."""

from __future__ import annotations

from .config import InstanceProfile
from .exceptions import ConfigError
from .ilias import IliasBackend
from .moodle import MoodleBackend


class BackendProtocol:
    """Protocol für Backend-Klassen (duck typing)."""

    def login(self, username: str, password: str, **kwargs) -> "LoginResult": ...
    def status(self) -> "StatusResult": ...
    def logout(self) -> "LogoutResult": ...
    def close(self) -> None: ...


def create_backend(instance: InstanceProfile, config_dir: str | None = None) -> BackendProtocol:
    """Erstellt das passende Backend basierend auf instance.lms."""
    if instance.lms == "moodle":
        return MoodleBackend(instance, config_dir)
    if instance.lms == "ilias":
        return IliasBackend(instance, config_dir)
    raise ConfigError(f"Unbekanntes LMS: {instance.lms}. Erwartet: 'moodle' oder 'ilias'")