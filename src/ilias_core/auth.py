"""Auth-Service: verbindet Konfiguration, Backend und Token-Speicher (F1)."""

from __future__ import annotations

from .backends import get_backend
from .config import InstanceConfig
from .errors import NotLoggedInError
from .models import LoginResult, LogoutResult, StatusResult, now_berlin
from .session import TokenStore


class AuthService:
    def __init__(self, config: InstanceConfig, store: TokenStore | None = None) -> None:
        self.config = config
        self.store = store or TokenStore(config.config_dir, config.lms, config.instance)

    def login(self, username: str, password: str) -> LoginResult:
        backend = get_backend(self.config)
        try:
            token = backend.get_token(username, password)
            # Erst verifizieren, dann speichern (Task-Vorgabe).
            info = backend.get_site_info(token)
        finally:
            backend.close()
        self.store.save(token)
        return LoginResult(
            lms=self.config.lms,
            instance=self.config.instance,
            base_url=self.config.base_url,
            username=info.username or username,
            fullname=info.fullname,
            sitename=info.sitename,
            userid=info.userid,
            logged_in_at=now_berlin(),
        )

    def status(self) -> StatusResult:
        token = self.store.load()
        if not token:
            raise NotLoggedInError("Nicht eingeloggt: kein gespeicherter Token.")
        backend = get_backend(self.config)
        try:
            info = backend.get_site_info(token)
        finally:
            backend.close()
        return StatusResult(
            lms=self.config.lms,
            instance=self.config.instance,
            base_url=self.config.base_url,
            username=info.username,
            fullname=info.fullname,
            sitename=info.sitename,
            userid=info.userid,
            valid=True,
            checked_at=now_berlin(),
        )

    def logout(self) -> LogoutResult:
        removed = self.store.delete()
        return LogoutResult(
            lms=self.config.lms,
            instance=self.config.instance,
            base_url=self.config.base_url,
            removed=removed,
            logged_out_at=now_berlin(),
        )
