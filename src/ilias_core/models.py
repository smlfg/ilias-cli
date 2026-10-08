"""Datenmodelle für Moodle und ILIAS (Pydantic/Dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class MoodleTokenResponse:
    """Antwort von /login/token.php."""

    token: str
    privatetoken: str | None = None
    error: str | None = None
    errorcode: str | None = None
    debuginfo: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MoodleTokenResponse:
        return cls(
            token=data.get("token", ""),
            privatetoken=data.get("privatetoken"),
            error=data.get("error"),
            errorcode=data.get("errorcode"),
            debuginfo=data.get("debuginfo"),
        )

    def is_error(self) -> bool:
        return bool(self.error or self.errorcode)


@dataclass
class MoodleSiteInfo:
    """Antwort von core_webservice_get_site_info."""

    sitename: str
    username: str
    fullname: str
    userid: int
    siteurl: str
    functions: list[dict[str, Any]] | None = None
    downloadfiles: int | None = None
    userpictureurl: str | None = None
    lang: str | None = None
    mobilecssurl: str | None = None
    calendartype: str | None = None
    errorcode: str | None = None
    exception: str | None = None
    message: str | None = None
    debuginfo: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> MoodleSiteInfo:
        return cls(
            sitename=data.get("sitename", ""),
            username=data.get("username", ""),
            fullname=data.get("fullname", ""),
            userid=data.get("userid", 0),
            siteurl=data.get("siteurl", ""),
            functions=data.get("functions"),
            downloadfiles=data.get("downloadfiles"),
            userpictureurl=data.get("userpictureurl"),
            lang=data.get("lang"),
            mobilecssurl=data.get("mobilecssurl"),
            calendartype=data.get("calendartype"),
            errorcode=data.get("errorcode"),
            exception=data.get("exception"),
            message=data.get("message"),
            debuginfo=data.get("debuginfo"),
        )

    def is_error(self) -> bool:
        return bool(self.errorcode or self.exception)

    def is_invalid_token(self) -> bool:
        return self.errorcode == "invalidtoken" or "invalid token" in (self.message or "").lower()


@dataclass
class LoginResult:
    """Strukturierter Rückgabewert für login."""

    success: bool
    instance_name: str
    lms: str
    base_url: str
    username: str | None = None
    fullname: str | None = None
    sitename: str | None = None
    token: str | None = None  # wird nur intern genutzt, nie in JSON ausgegeben
    error: str | None = None
    errorcode: str | None = None
    exit_code: int = 0

    def to_json(self, include_token: bool = False) -> dict[str, Any]:
        """JSON-Ausgabe für --json (ohne Token)."""
        data = {
            "success": self.success,
            "instance": self.instance_name,
            "lms": self.lms,
            "base_url": self.base_url,
            "exit_code": self.exit_code,
        }
        if self.username:
            data["username"] = self.username
        if self.fullname:
            data["fullname"] = self.fullname
        if self.sitename:
            data["sitename"] = self.sitename
        if self.error:
            data["error"] = self.error
        if self.errorcode:
            data["errorcode"] = self.errorcode
        if include_token and self.token:
            data["token"] = self.token
        return data


@dataclass
class StatusResult:
    """Strukturierter Rückgabewert für status."""

    success: bool
    instance_name: str
    lms: str
    base_url: str
    logged_in: bool
    username: str | None = None
    fullname: str | None = None
    sitename: str | None = None
    token_valid: bool = False
    last_checked: datetime | None = None
    error: str | None = None
    errorcode: str | None = None
    exit_code: int = 0

    def to_json(self) -> dict[str, Any]:
        data = {
            "success": self.success,
            "instance": self.instance_name,
            "lms": self.lms,
            "base_url": self.base_url,
            "logged_in": self.logged_in,
            "token_valid": self.token_valid,
            "exit_code": self.exit_code,
        }
        if self.last_checked:
            data["last_checked"] = self.last_checked.isoformat()
        if self.username:
            data["username"] = self.username
        if self.fullname:
            data["fullname"] = self.fullname
        if self.sitename:
            data["sitename"] = self.sitename
        if self.error:
            data["error"] = self.error
        if self.errorcode:
            data["errorcode"] = self.errorcode
        return data


@dataclass
class LogoutResult:
    """Strukturierter Rückgabewert für logout."""

    success: bool
    instance_name: str
    lms: str
    base_url: str
    had_session: bool = False
    error: str | None = None
    exit_code: int = 0

    def to_json(self) -> dict[str, Any]:
        data = {
            "success": self.success,
            "instance": self.instance_name,
            "lms": self.lms,
            "base_url": self.base_url,
            "had_session": self.had_session,
            "exit_code": self.exit_code,
        }
        if self.error:
            data["error"] = self.error
        return data


# ILIAS Models (Platzhalter für spätere Implementierung)
@dataclass
class IliasSession:
    """ILIAS Session-Cookies."""

    phpsessid: str
    il_client_id: str
    base_url: str
    client_id: str