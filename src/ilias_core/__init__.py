"""Kernbibliothek: Auth, Session, Config, Modelle. Skeleton auf main, Implementierung auf attempt/*-Branches."""

from .moodle import MoodleAuth, MoodleConfig, MoodleSession, InvalidLoginError as MoodleAuthError

__version__ = "0.0.0"
