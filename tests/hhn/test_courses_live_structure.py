"""F2 `ilias courses` (S6): zusätzliche Tests aus den Live-Befunden vom 08.10.

Spec: docs/HHN_2FA_SPEC.md §13.1, §13.2. Nur synthetische Fixtures (tests/hhn/fixtures/, bedient von
tests/hhn/fake_hhn.py), deren Markup der echten HHN-Struktur folgt. Jeder Test nennt den Spec-Punkt.
Eigener Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_courses*.py -q`
"""

from __future__ import annotations

from .conftest import HhnHarness
from .fixtures.courses.data import EXPECTED_SEMESTER, FAVORITES, MEMBERSHIPS
from .helpers import ok_json


def test_courses_only_from_membership_overview(logged_in: HhnHarness):
    """§13.2: Kursliste nur aus ilmembershipoverviewgui (Dashboard = Favoriten-Teilmenge);
    il-item-Einträge außerhalb des Hauptinhalts (Metabar-Benachrichtigung mit "Zeit") zählen nicht."""
    n_before = len(logged_in.world.requests)
    data = ok_json(logged_in.run("courses", "--json"))
    assert len(FAVORITES) < data["count"] == len(MEMBERSHIPS)
    base_classes = [r.query.get("baseClass", [""])[0].lower() for r in logged_in.world.requests[n_before:]]
    assert "ilmembershipoverviewgui" in base_classes, base_classes
    titles = [c["fullname"] for c in data["courses"]]
    assert "Neue Nachricht im Beispielforum" not in titles and "Favoriten" not in titles


def test_courses_semester_hhn_title_patterns(logged_in: HhnHarness):
    """§5.3/§13.2: HHN-Titelformen `_WS26_27`, `2026 WS`, `WiSe26/27` -> "WiSe 2026/27"; "Anmeldungsende"
    (hier im März) bestimmt das Semester nicht."""
    data = ok_json(logged_in.run("courses", "--json"))
    got = {c["id"]: c["semester"] for c in data["courses"]}
    for ref in (900106, 900107, 900108, 900109):
        assert got[ref] == EXPECTED_SEMESTER[ref] == "WiSe 2026/27", (ref, got[ref])


def test_courses_ids_are_ref_ids_not_course_numbers(logged_in: HhnHarness):
    """§13.1: id = ref_id aus dem Permalink `/go/<typ>/<ref>`, nie die Kursnummer aus Titel/Beschreibung."""
    data = ok_json(logged_in.run("courses", "--json"))
    ids = {c["id"] for c in data["courses"]}
    assert ids == {m["ref_id"] for m in MEMBERSHIPS}
    assert not ids & {990041, 990077}
