"""Strukturierte Modelle (keine Secrets, keine Tokens in Reprs)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteInfo:
    sitename: str
    username: str
    fullname: str
    userid: int | str


@dataclass(frozen=True)
class ResolvedConfig:
    instance: str | None
    lms: str
    base_url: str
