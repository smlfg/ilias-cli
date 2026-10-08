"""HTTP-Helfer: eigener User-Agent, sinnvolle Timeouts, sicheres Debug-Logging."""

from __future__ import annotations

import httpx

from . import debuglog
from .config import Config
from .version import __version__

USER_AGENT = f"ilias-cli/{__version__}"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def build_client(config: Config, *, follow_redirects: bool = True) -> httpx.Client:
    """Erzeugt einen ``httpx.Client`` mit eigenem User-Agent und Timeout."""

    return httpx.Client(
        follow_redirects=follow_redirects,
        timeout=DEFAULT_TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        event_hooks=debuglog.EVENT_HOOKS,
    )
