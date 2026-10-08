"""Klartext aus HTML (Moodle liefert Namen/Beschreibungen/availabilityinfo als HTML).

Ohne zusätzliche Abhängigkeit: `html.parser` sammelt den Text, Entities werden
durch `convert_charrefs` aufgelöst, Weißraum wird zusammengefasst.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

ELLIPSIS = "…"
_LABEL_LIMIT = 60
_WHITESPACE = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]*>")
_BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "div", "dd", "dl", "dt",
        "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
        "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
        "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
    }
)


class _TextExtractor(HTMLParser):
    """Sammelt den sichtbaren Text und setzt an Block-Elementen Trennzeichen."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def _break(self) -> None:
        if self.parts and not self.parts[-1].endswith(" "):
            self.parts.append(" ")

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _BLOCK_TAGS:
            self._break()

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in _BLOCK_TAGS:
            self._break()

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._break()

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(value: str | None) -> str:
    """HTML -> einzeiliger Klartext (Entities aufgelöst, Tags entfernt)."""
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
        text = "".join(parser.parts)
    except Exception:  # pragma: no cover - kaputtes HTML: grobe Entfernung
        text = _TAGS.sub(" ", value)
    return _WHITESPACE.sub(" ", text).strip()


def plain_text(value: str | None, *, limit: int | None = None) -> str:
    """Klartext, optional auf `limit` Zeichen gekürzt (mit `…`)."""
    text = strip_html(value)
    if limit is not None and len(text) > limit:
        text = text[: max(limit - 1, 0)].rstrip() + ELLIPSIS
    return text


def label(value: str | None, *, limit: int = _LABEL_LIMIT, fallback: str = "") -> str:
    """Kurzer Anzeigename (z. B. für `label`-Module): Klartext, höchstens `limit` Zeichen."""
    text = plain_text(value, limit=limit)
    return text or fallback
