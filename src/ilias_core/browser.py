"""Optionales Browser-Login-Verfahren (Playwright).

Playwright ist ein optionales Extra (``[project.optional-dependencies].browser``)
und wird deshalb erst zur Laufzeit importiert. Der Browser ist **sichtbar**,
der Nutzer meldet sich selbst an, danach werden ausschließlich die
ILIAS-Cookies übernommen. In Tests wird diese Funktion gemockt.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .errors import AuthenticationError, BrowserUnavailableError

DEFAULT_TIMEOUT = 300


def login_with_browser(base_url: str, *, timeout: int = DEFAULT_TIMEOUT) -> dict[str, str]:
    """Öffnet einen sichtbaren Browser und übernimmt die ILIAS-Cookies."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - hängt von der Umgebung ab
        raise BrowserUnavailableError(
            "Playwright ist nicht installiert. Installiere das optionale Extra mit "
            "`uv sync --extra browser` (oder `pip install 'ilias-cli[browser]'`) "
            "und führe anschließend `playwright install chromium` aus."
        ) from exc

    base_url = base_url.rstrip("/")
    host = (urlparse(base_url).hostname or "").lower()
    timeout_ms = timeout * 1000

    with sync_playwright() as playwright:  # pragma: no cover - nur live
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"{base_url}/openidconnect.php")
            page.wait_for_url(f"**{host}/**", timeout=timeout_ms)
            cookies = _extract_ilias_cookies(context.cookies(), host)
        finally:
            browser.close()

    if not cookies:
        raise AuthenticationError("Keine ILIAS-Cookies aus dem Browser übernommen.")
    return cookies


def _extract_ilias_cookies(raw_cookies: list[dict], host: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for cookie in raw_cookies:
        domain = (cookie.get("domain") or "").lstrip(".").lower()
        name = cookie.get("name")
        if not domain or not name:
            continue
        if host == domain or host.endswith("." + domain):
            cookies[name] = cookie.get("value", "")
    return cookies
