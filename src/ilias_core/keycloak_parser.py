from __future__ import annotations

from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser as HTMLParser


@dataclass
class FormDescription:
    action: str
    method: str
    hidden: dict[str, str] = field(default_factory=dict)
    fields: set[str] = field(default_factory=set)


def _extract_form(html: str, form_id: str) -> FormDescription | None:
    tree = HTMLParser(html)
    node = tree.css_first(f"form#{form_id}")
    if node is None:
        return None
    action = node.attributes.get("action")
    if not action:
        return None
    method = (node.attributes.get("method") or "post").lower()
    hidden: dict[str, str] = {}
    fields: set[str] = set()
    for inp in node.css("input"):
        name = inp.attributes.get("name")
        if not name:
            continue
        typ = (inp.attributes.get("type") or "text").lower()
        if typ == "hidden":
            hidden[name] = inp.attributes.get("value") or ""
        fields.add(name)
    return FormDescription(action=action, method=method, hidden=hidden, fields=fields)


def parse_login_form(html: str) -> FormDescription | None:
    return _extract_form(html, "kc-form-login")


def parse_totp_form(html: str) -> FormDescription | None:
    return _extract_form(html, "kc-otp-login-form")


def parse_error_message(html: str) -> str | None:
    tree = HTMLParser(html)
    node = tree.css_first("#input-error") or tree.css_first(".alert-error") or tree.css_first("#kc-content-feedback")
    if node is None:
        return None
    text = node.text(strip=True)
    return text or None


def looks_like_login_page(html: str) -> bool:
    return parse_login_form(html) is not None
