"""HTTP-Client-Factory: eigener User-Agent, sinnvolle Timeouts."""

from __future__ import annotations

import httpx

from ilias_core import __version__

USER_AGENT = f"ilias-cli/{__version__}"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def create_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Erstellt den HTTP-Client.

    ``transport`` kann für Tests (``httpx.MockTransport``) injiziert werden.
    Redirects werden gefolgt, damit der Keycloak-Flow automatisch durchläuft.
    """
    return httpx.Client(
        transport=transport,
        follow_redirects=True,
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
