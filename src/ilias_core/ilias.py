"""ILIAS Backend (Platzhalter für spätere Implementierung)."""

from __future__ import annotations

from .config import InstanceProfile
from .exceptions import NotLoggedInError
from .models import LoginResult, LogoutResult, StatusResult


class IliasBackend:
    """ILIAS Backend - noch nicht implementiert."""

    def __init__(self, instance: InstanceProfile, config_dir: str | None = None):
        self.instance = instance
        self.base_url = instance.base_url.rstrip("/")

    def login(self, username: str, password: str, totp: str | None = None) -> LoginResult:
        raise NotImplementedError("ILIAS Backend nicht implementiert")

    def status(self) -> StatusResult:
        raise NotLoggedInError("ILIAS Backend nicht implementiert")

    def logout(self) -> LogoutResult:
        return LogoutResult(
            success=True,
            instance_name=self.instance.name,
            lms="ilias",
            base_url=self.base_url,
            had_session=False,
            exit_code=0,
        )

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()