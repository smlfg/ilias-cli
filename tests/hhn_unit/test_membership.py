"""Unit-Tests für den Mitgliedschafts-Parser ("Meine Kurse und Gruppen").

Nur synthetisches HTML nach Spec §13.2. Wichtig: Der Metabar enthält ebenfalls
``.il-item`` mit der Eigenschaft "Zeit" – das darf nie als Kurs/Semester zählen.
"""

from __future__ import annotations

from ilias_core.ilias_html.membership import (
    has_membership_structure,
    is_empty_membership,
    parse_memberships,
)

HTML = """
<!DOCTYPE html><html><body>
<header><ul class="il-maincontrols-metabar">
 <li><div class="il-item il-notification-item"><div class="media"><div class="media-body">
  <h4 class="il-item-title">Neue Nachricht</h4>
  <span class="il-item-property-name">Zeit</span><span class="il-item-property-value">6. Okt 2026, 14:20</span>
 </div></div></div></li>
</ul></header>
<div id="ilContentContainer"><div class="panel-body">
 <div class="il-item-group"><h3>Fachgruppe</h3><div class="il-item-group-items"><ul>
  <li class="il-std-item-container"><div class="il-item il-std-item"><div class="media">
   <div class="media-left"><img alt="Kurs" class="icon custom medium" src="./templates/default/images/standard/icon_crs.svg"/></div>
   <div class="media-body">
    <h4 class="il-item-title"><a href="https://ilias.example.org/go/crs/900101">Mathematik A (WiSe 2026/27)</a></h4>
    <div class="il-item-actions"><button data-action="leave">x</button></div>
    <div class="il-item-description">Beispielbeschreibung</div>
    <div class="row"><span class="il-item-property-name"></span><span class="il-item-property-value">Keine freien Plätze</span></div>
   </div></div></div></li>
  <li class="il-std-item-container"><div class="il-item il-std-item"><div class="media">
   <div class="media-left"><img alt="Gruppe" class="icon custom medium" src="./templates/default/images/standard/icon_grp.svg"/></div>
   <div class="media-body">
    <h4 class="il-item-title"><a href="https://ilias.example.org/go/grp/900105">Lerngruppe</a></h4>
    <span class="il-item-property-name">Status</span><span class="il-item-property-value">Offline</span>
   </div></div></div></li>
 </ul></div></div>
</div></div>
</body></html>
"""


def test_parse_memberships_main_content_only():
    memberships = parse_memberships(HTML, "https://ilias.example.org")
    assert [m.ref_id for m in memberships] == [900101, 900105]
    first, group = memberships
    assert first.type == "crs" and first.fullname == "Mathematik A (WiSe 2026/27)"
    assert first.semester == "WiSe 2026/27"
    assert first.description == "Beispielbeschreibung"
    assert first.url == "https://ilias.example.org/go/crs/900101"
    assert group.type == "grp" and group.visible is False
    # Benachrichtigung "Neue Nachricht"/"Zeit" niemals als Kurs
    assert "Neue Nachricht" not in [m.fullname for m in memberships]


def test_membership_structure_and_empty():
    assert has_membership_structure(HTML) is True
    assert is_empty_membership(HTML) is False
    empty = '<div id="ilContentContainer"><div class="panel-body"><div class="alert-info">leer</div></div></div>'
    assert is_empty_membership(empty) is True
    assert parse_memberships(empty, "https://x") == []
    assert has_membership_structure("<h1>Wartung</h1>") is False
