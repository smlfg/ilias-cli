"""Data models for ILIAS CLI."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class SessionCookies:
    """ILIAS session cookies - never logged or serialized to JSON output."""

    phpsessid: str
    il_client_id: str
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for storage."""
        result = {
            "PHPSESSID": self.phpsessid,
            "ilClientId": self.il_client_id,
        }
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> SessionCookies:
        """Create from dictionary."""
        phpsessid = data.get("PHPSESSID", "")
        il_client_id = data.get("ilClientId", "")
        extra = {k: v for k, v in data.items() if k not in ("PHPSESSID", "ilClientId")}
        return cls(phpsessid=phpsessid, il_client_id=il_client_id, extra=extra)

    def get_cookie_header(self) -> str:
        """Get Cookie header value."""
        parts = []
        if self.phpsessid:
            parts.append(f"PHPSESSID={self.phpsessid}")
        if self.il_client_id:
            parts.append(f"ilClientId={self.il_client_id}")
        for k, v in self.extra.items():
            parts.append(f"{k}={v}")
        return "; ".join(parts)


class LoginResult(BaseModel):
    """Result of a login attempt."""

    success: bool
    message: str
    cookies: SessionCookies | None = None

    # For JSON output - cookies are excluded
    def model_dump_json_safe(self, **kwargs) -> str:
        """Dump to JSON without cookies."""
        data = self.model_dump(exclude={"cookies"}, **kwargs)
        return data


class SessionStatus(BaseModel):
    """Status of the current session."""

    logged_in: bool
    message: str
    username: str | None = None
    expires_at: str | None = None  # ISO 8601 if known

    def model_dump_json_safe(self, **kwargs) -> str:
        """Dump to JSON (same as model_dump_json for this model)."""
        return self.model_dump_json(**kwargs)


class LogoutResult(BaseModel):
    """Result of a logout operation."""

    success: bool
    message: str