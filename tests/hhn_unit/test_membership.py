"""Unit-Tests für ilias_credits.ilias_html.membership (Spec §5.2/§13.2), synthetisches HTML."""

from __future__ import annotations

import pytest

from ilias_core.errors import ParserError
from ilias_core.ilias_html.membership import parse_memberships

BASE = "https://ilias.example.org"


def _item(ref, typ, title, desc="", props=()):
    href = f"{BASE}/go/{typ}/{ref}"
    prop_html = ""
    if props:
        cells = "".join(
            f'<div class="col-md-6 il-multi-line-cap-3"><span class="il-item-property-name">{k}</span>'
            f'<span class="il-item-property-value">{v}</span></div>'
            for k, v in props
        )
        prop_html = f'<hr class="il-item-divider"/><div class="row">{cells}</div>'
    desc_html = f'<div class="il-item-description">{desc}</div>' if desc else ""
    return (
        f'<li class="il-std-item-container"><div class="il-item il-std-item"><div class="media">'
        f'<div class="media-body"><h4 class="il-item-title"><a href="{href}">{title}</a></h4>'
        f"<div class=\"il-item-actions\"></div>{desc_html}{prop_html}"
        f"</div></div></div></li>"
    )


def _page(body: str, metabar: str = "") -> str:
    return (
        "<html><body>"
        f'<header>{metabar}</header>'
        '<div id="ilContentContainer"><div class="row"><div class="col-sm-12" id="il_center_col">'
        '<div class="panel panel-secondary panel-flex"><div class="panel-body">'
        f"{body}</div></div></div></div></div>"
        "</body></html>"
    )


def test_parse_basic_fields():
    html = _page(
        '<div class="il-item-group"><h3>Kategorie</h3><div class="il-item-group-items"><ul>'
        + _item(900101, "crs", "Mathematik A (WiSe 2026/27)", desc="TS9 990041")
        + _item(900105, "grp", "Lerngruppe Synthese")
        + "</ul></div></div>"
    )
    courses = parse_memberships(html, BASE)
    assert [c.id for c in courses] == [900101, 900105]
    c1, c2 = courses
    assert c1.course_type == "crs" and c2.course_type == "grp"
    assert c1.fullname == "Mathematik A (WiSe 2026/27)"
    assert c1.shortname == ""
    assert c1.semester == "WiSe 2026/27"
    assert c1.visible is True
    assert c1.url == f"{BASE}/go/crs/900101"
    assert c1.startdate is None and c1.enddate is None and c1.category is None
    assert c1.description == "TS9 990041"
    assert c2.semester is None


def test_metabar_notification_ignored():
    metabar = (
        '<ul class="il-maincontrols-metabar"><li><div class="il-item il-notification-item">'
        '<div class="media-body"><h4 class="il-item-notification-title">Neue Nachricht</h4>'
        '<span class="il-item-property-name">Zeit</span>'
        '<span class="il-item-property-value">6. Okt 2026, 14:20</span>'
        "</div></div></li></ul>"
    )
    html = _page(
        '<div class="il-item-group"><div class="il-item-group-items"><ul>'
        + _item(900101, "crs", "Kurs A")
        + "</ul></div></div>",
        metabar=metabar,
    )
    courses = parse_memberships(html, BASE)
    assert [c.id for c in courses] == [900101]
    assert courses[0].semester is None


def test_semester_from_period_property_wins():
    html = _page(
        '<ul>' + _item(900102, "crs", "Mathematik B", props=[("Zeitraum", "16. Mär 2026 - 31. Aug 2026")]) + "</ul>"
    )
    (course,) = parse_memberships(html, BASE)
    assert course.semester == "SoSe 2026"


def test_course_number_props_do_not_set_semester():
    html = _page(
        "<ul>"
        + _item(900106, "crs", "Traumwirtschaft_Beispiel_WS26_27",
                props=[("Anmeldungsende", "31. Mär 2027, 12:00"), ("", "Keine freien Plätze verfügbar")])
        + "</ul>"
    )
    (course,) = parse_memberships(html, BASE)
    assert course.semester == "WiSe 2026/27"


def test_offline_property():
    html = _page("<ul>" + _item(900104, "crs", "Archivkurs", props=[("Status", "Offline")]) + "</ul>")
    (course,) = parse_memberships(html, BASE)
    assert course.visible is False


def test_empty_hint_returns_empty_list():
    html = _page('<div class="alert alert-info">Sie sind noch keinem Kurs beigetreten.</div>')
    assert parse_memberships(html, BASE) == []


def test_garbage_page_raises():
    with pytest.raises(ParserError):
        parse_memberships("<html><body><h1>Wartungsarbeiten</h1></body></html>", BASE)


def test_duplicate_ref_id_kept_once():
    html = _page("<ul>" + _item(900101, "crs", "A") + _item(900101, "crs", "A") + "</ul>")
    assert len(parse_memberships(html, BASE)) == 1


def test_entities_and_nfc():
    html = _page("<ul>" + _item(900101, "crs", "Dienste --&gt; Unterst&uuml;tzung") + "</ul>")
    (course,) = parse_memberships(html, BASE)
    assert course.fullname == "Dienste --> Unterstützung"
