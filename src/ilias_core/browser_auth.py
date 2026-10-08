from __future__ import annotations

from .errors import BrowserUnavailableError, ParserError
from .models import SessionData


def login_with_browser(base_url: str, timeout_ms: int = 300_000) -> SessionData:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailableError(
            "Playwright ist nicht installiert. Installiere es mit: uv sync --extra browser "
            "und führe danach 'uv run playwright install chromium' aus."
        ) from exc

    cookies: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"{base_url}/openidconnect.php")
            page.wait_for_url("**/ilias.php**", timeout=timeout_ms)
            for cookie in context.cookies():
                cookies[cookie["name"]] = cookie["value"]
        finally:
            browser.close()
    if not any(n == "PHPSESSID" for n in cookies):
        raise ParserError("Keine ILIAS-Session-Cookies im Browser gefunden")
    return SessionData(base_url=base_url, cookies=cookies)
