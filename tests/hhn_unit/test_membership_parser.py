"""Unit-Tests des reinen Mitgliedschafts-Parsers (Spec §5.2/§13.2, S6).

Synthetisches HTML (keine Fixtures aus tests/hhn) mit derselben Struktur wie die
Live-Seite. Geprüft werden: nur der Hauptinhalt, nur der Titel-Link, ref_id statt
Kursnummer, Entities/NFC, Offline, Semester nur aus dem Titel/Zeitraum.
"""

from __future__ import annotations

import pytest

from ilias_core.errors import ParserError
from ilias_core.ilias_html.membership import parse_memberships

BASE = "https://ilias.example.org"

# Metabar-Benachrichtigung mit Eigenschaft "Zeit" -> darf nie Kurs/Semester werden.
HTML = """
<!DOCTYPE html><html><body>
<ul class="il-maincontrols-metabar" role="menubar">
  <li><div class="il-item il-notification-item"><div class="media"><div class="media-body">
    <h4 class="il-item-notification-title">Neue Nachricht im Beispielforum</h4>
    <div class="il-item-description">Synthetisch</div>
    <div class="row il-item-properties"><div class="il-multi-line-cap-3">
      <span class="il-item-property-name">Zeit</span>
      <span class="il-item-property-value">6. Okt 2026, 14:20</span>
    </div></div>
  </div></div></div></li>
  <li><a href="/logout.php?baseClass=ilstartupgui&amp;cmd=doLogout">Abmelden</a></li>
</ul>
<div id="ilContentContainer"><div class="row"><div class="col-sm-12" id="il_center_col">
  <div class="panel panel-secondary panel-flex">
    <div class="panel-heading"><div class="panel-title"><h2>Meine Kurse und Gruppen</h2></div></div>
    <div class="panel-body">
      <div class="il-item-group"><h3>Fachgruppe Rechenkunst</h3>
      <div class="il-item-group-items"><ul>
        <li class="il-std-item-container"><div class="il-item il-std-item"><div class="media">
          <div class="media-left"><img alt="Kurs" class="icon custom medium"
            src="./templates/default/images/standard/icon_crs.svg"/></div>
          <div class="media-body">
            <h4 class="il-item-title"><a href="https://ilias.example.org/go/crs/900101">Mathematik &amp; Statistik (WiSe 2026/27)</a></h4>
            <div class="il-item-actions"><button data-action="ilias.php?cmd=leave&amp;ref_id=900101">Beenden</button></div>
            <div class="il-item-description">Kursnummer 990041</div>
            <hr class="il-item-divider"/><div class="row">
              <div class="col-md-6 il-multi-line-cap-3">
                <span class="il-item-property-name">Anmeldungsende</span>
                <span class="il-item-property-value">31. Mär 2027, 12:00</span></div>
            </div>
          </div></div></div></li>
        <li class="il-std-item-container"><div class="il-item il-std-item"><div class="media">
          <div class="media-left"><img alt="Gruppe" class="icon custom medium"
            src="./templates/default/images/standard/icon_grp.svg"/></div>
          <div class="media-body">
            <h4 class="il-item-title"><a href="https://ilias.example.org/go/grp/900105">Lerngruppe Synthese</a></h4>
            <hr class="il-item-divider"/><div class="row">
              <div class="col-md-6 il-multi-line-cap-3">
                <span class="il-item-property-name">Status</span>
                <span class="il-item-property-value">Offline</span></div>
            </div>
          </div></div></div></li>
      </ul></div></div>
    </div>
  </div>
</div></div></div>
</body></html>
"""


def test_parse_memberships_fields():
    courses = parse_memberships(HTML, BASE)
    assert [c.id for c in courses] == [900101, 900105]

    math = courses[0]
    assert math.fullname == "Mathematik & Statistik (WiSe 2026/27)"
    assert math.type == "crs"
    assert math.url == f"{BASE}/go/crs/900101"
    assert math.semester == "WiSe 2026/27"  # aus dem Titel
    assert math.visible is True
    assert math.description == "Kursnummer 990041"  # für die Kursnummernsuche in `ls`
    assert math.shortname == ""
    assert math.startdate is None and math.enddate is None and math.category is None

    group = courses[1]
    assert group.type == "grp"
    assert group.url == f"{BASE}/go/grp/900105"
    assert group.semester is None
    assert group.visible is False


def test_metabar_notification_never_becomes_a_course():
    titles = [c.fullname for c in parse_memberships(HTML, BASE)]
    assert "Neue Nachricht im Beispielforum" not in titles
    assert len(parse_memberships(HTML, BASE)) == 2


def test_empty_membership_page_is_empty_list():
    empty = (
        '<div id="ilContentContainer"><div class="panel-body">'
        '<div class="alert alert-info" role="status">'
        "Sie sind noch keinem Kurs und keiner Gruppe beigetreten.</div>"
        "</div></div>"
    )
    assert parse_memberships(empty, BASE) == []


def test_page_without_list_and_empty_hint_raises_parse_error():
    garbage = "<!DOCTYPE html><html><body><h1>Wartungsarbeiten</h1></body></html>"
    with pytest.raises(ParserError) as excinfo:
        parse_memberships(garbage, BASE)
    assert "Meine Kurse und Gruppen" in excinfo.value.message
