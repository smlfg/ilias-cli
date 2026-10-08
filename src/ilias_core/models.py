from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SessionData(BaseModel):
    base_url: str
    cookies: dict[str, str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LoginResult(BaseModel):
    ok: bool
    base_url: str
    created_at: datetime


class SessionStatus(BaseModel):
    logged_in: bool
    base_url: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
