"""Browser-Login-Fallback (``ilias login --browser``).

Der Login läuft in einem SICHTBAREN Playwright-Browserfenster; der Nutzer
loggt sich selbst ein. Danach werden nur die ILIAS-Cookies übernommen.

Playwright ist ein optionales Extra und wird lazy importiert. In Tests
wird diese Funktion gemockt - es wird kein echter Browser gestartet.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

from ilias_core.errors import BrowserLoginError
from ilias_core.models import LoginResult

DEFAULT_TIMEOUT = 180.0


def _extract_cookies(cookie_list: list[dict], base_url: str) -> dict[str, str]:
    host = urlparse(base_url).hostname or ""
    cookies: dict[str, str] = {}
    for c in cookie_list:
        domain = (c.get("domain") or "").lstrip(".")
        if domain and host and (host == domain or host.endswith(f".{domain}")):
            cookies[c["name"]] = c["value"]
    return cookies


def login_with_browser(
    base_url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> LoginResult:
    """Sichtbaren Browser öffnen, Nutzer einloggen lassen, Cookies übernehmen."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserLoginError(
            "Playwright ist nicht installiert. "
            "Installiere das optionale Extra: pip install 'ilias-cli[browser]'"
        ) from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(f"{base_url}/openidconnect.php", wait_until="domcontentloaded")

                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    url = page.url
                    if (
                        url.startswith(base_url)
                        and "openidconnect" not in url
                        and "login" not in url
                    ):
                        break
                    time.sleep(0.5)
                else:
                    raise BrowserLoginError(
                        "Login im Browser abgelaufen (Timeout) - bitte erneut versuchen"
                    )

                cookies = _extract_cookies(context.cookies(), base_url)
                final_url = page.url
            finally:
                browser.close()
    except BrowserLoginError:
        raise
    except Exception as exc:  # PlaywrightError u. a.
        raise BrowserLoginError(f"Browser-Login fehlgeschlagen: {exc}") from exc

    if not cookies:
        raise BrowserLoginError(
            "Login abgeschlossen, aber keine Session-Cookies erhalten"
        )
    return LoginResult(cookies=cookies, final_url=final_url)
