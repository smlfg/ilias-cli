"""Structured data models (no formatted text, no secrets)."""

from __future__ import annotations

from pydantic import BaseModel


class LoginResult(BaseModel):
    success: bool
    base_url: str
    username: str | None = None
    message: str = ""


class SessionStatus(BaseModel):
    logged_in: bool
    base_url: str
    username: str | None = None
    expired: bool = False
    message: str = ""

    def to_public_dict(self) -> dict:
        """JSON-safe dict without any cookies/secrets."""
        return self.model_dump()
