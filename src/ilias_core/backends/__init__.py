"""Backend-Registry: wählt anhand ``lms`` die passende Implementierung."""

from __future__ import annotations

from ..config import InstanceConfig
from .base import Backend
from .moodle import MoodleBackend


def get_backend(config: InstanceConfig) -> Backend:
    if config.lms == "moodle":
        return MoodleBackend(config)
    raise NotImplementedError(
        f"Das LMS {config.lms!r} wird noch nicht unterstützt."
    )
