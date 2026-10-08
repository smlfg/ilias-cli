"""F2 `ilias courses` für die ILIAS-Instanz `hhn` (HTML-Scraping), Bau-Schritt S6.

Spec: docs/HHN_2FA_SPEC.md §5, §7. Nur synthetische Fixtures (tests/hhn/fixtures/, bedient von
tests/hhn/fake_hhn.py), deren Markup der echten HHN-Struktur folgt. Jeder Test nennt den Spec-Punkt.
Eigener Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_courses*.py -q`
"""

from __future__ import annotations

import json

from .conftest import HhnHarness
from .fixtures.courses.data import EXPECTED_SEMESTER, MEMBERSHIPS
from .helpers import err_json, ok_json


def test_courses_help_has_json_and_instance(hh: HhnHarness):
    """§5.1: `courses` existiert mit `--json` und `--instance`."""
    r = hh.run("courses", "--help")
    assert r.exit_code == 0, str(r)
    assert "--json" in r.stdout and "--instance" in r.stdout


def test_courses_json_shape(logged_in: HhnHarness):
    """§5.1/§5.2: ein JSON-Objekt mit instance, lms=ilias, count, courses[]; id = ref_id (int)."""
    data = ok_json(logged_in.run("courses", "--json"))
    assert data["instance"] == "hhn"
    assert data["lms"] == "ilias"
    assert data["count"] == len(MEMBERSHIPS) == len(data["courses"])
    by_id = {c["id"]: c for c in data["courses"]}
    assert set(by_id) == {m["ref_id"] for m in MEMBERSHIPS}
    for m in MEMBERSHIPS:
        c = by_id[m["ref_id"]]
        assert c["fullname"] == m["title"]
        assert c["type"] == m["type"]
        assert c["url"].endswith(f"/go/{m['type']}/{m['ref_id']}"), c["url"]  # §13.1: HHN-Permalink
        assert c["url"].startswith(logged_in.world.ilias_base)


def test_courses_semester_derivation(logged_in: HhnHarness):
    """§5.3: Semester aus Titel (WiSe 2026/27, WS 2025/26) oder Zeitraum-Eigenschaft (März -> SoSe), sonst null."""
    data = ok_json(logged_in.run("courses", "--json"))
    got = {c["id"]: c["semester"] for c in data["courses"]}
    assert got == EXPECTED_SEMESTER


def test_courses_offline_marked(logged_in: HhnHarness):
    """§5.2: Offline-Kurse bleiben in der Liste, aber visible=false."""
    data = ok_json(logged_in.run("courses", "--json"))
    vis = {c["id"]: c["visible"] for c in data["courses"]}
    assert vis[900104] is False
    assert vis[900101] is True


def test_courses_human_table(logged_in: HhnHarness):
    """§5.1: Tabelle für Menschen mit ref_id und Titel; keine Cookies/Session-IDs."""
    r = logged_in.run("courses")
    assert r.exit_code == 0, str(r)
    for m in MEMBERSHIPS:
        assert str(m["ref_id"]) in r.stdout
    assert "Lerngruppe Synthese" in r.stdout
    for sid in logged_in.world.issued_session_ids:
        assert sid not in r.stdout + r.stderr


def test_courses_empty_membership_ok(logged_in: HhnHarness):
    """§5.2: Keine Mitgliedschaften = Exit 0, count 0 (kein Parser-Fehler)."""
    logged_in.world.membership_mode = "empty"
    data = ok_json(logged_in.run("courses", "--json"))
    assert data["count"] == 0 and data["courses"] == []


def test_courses_only_get_requests_no_relogin(logged_in: HhnHarness):
    """§4.3/N2: Lesen nur per GET, Session wird wiederverwendet (kein Keycloak-Kontakt nach Login)."""
    kc_before = len(logged_in.world.requests_to("keycloak"))
    n_before = len(logged_in.world.requests)
    ok_json(logged_in.run("courses", "--json"))
    new = logged_in.world.requests[n_before:]
    assert new, "courses hat ILIAS gar nicht gefragt"
    assert all(r.method == "GET" for r in new), [(r.method, r.path) for r in new]
    assert len(logged_in.world.requests_to("keycloak")) == kc_before, "courses darf keinen neuen Login starten"
    for r in new:
        assert r.headers.get("User-Agent", "").startswith("ilias-cli/"), r.headers


def test_courses_not_logged_in_exit2(hh: HhnHarness):
    """§4.4: keine Session -> Exit 2, error.code not_logged_in."""
    err_json(hh.run("courses", "--json"), 2, "not_logged_in")


def test_courses_session_expired_exit3_hint_no_relogin(logged_in: HhnHarness):
    """§4.4/A5: abgelaufene Session -> Exit 3, Hinweis auf `ilias login`/`ilias setup`, KEIN Auto-Re-Login."""
    logged_in.world.expire_all_sessions()
    kc_before = len(logged_in.world.requests_to("keycloak"))
    data = err_json(logged_in.run("courses", "--json"), 3, "session_expired")
    text = json.dumps(data, ensure_ascii=False)
    assert "ilias login" in text or "ilias setup" in text, data
    assert len(logged_in.world.requests_to("keycloak")) == kc_before


def test_courses_server_503_exit4(logged_in: HhnHarness):
    """§7: HTTP >= 500 -> Exit 4 (Status vor dem Parsen prüfen)."""
    logged_in.world.membership_mode = "error503"
    logged_in.world.dashboard_mode = "error503"
    err_json(logged_in.run("courses", "--json"), 4, "network_error")


def test_courses_unreachable_exit4(logged_in: HhnHarness):
    """§7: ILIAS nicht erreichbar -> Exit 4."""
    logged_in.world.stop_ilias()
    err_json(logged_in.run("courses", "--json"), 4, "network_error")


def test_courses_garbage_html_exit5(logged_in: HhnHarness):
    """§7: 200, aber weder Liste noch Leer-Hinweis noch Login-Merkmal -> Exit 5, kein Traceback."""
    logged_in.world.membership_mode = "garbage"
    logged_in.world.dashboard_mode = "error503"
    r = logged_in.run("courses", "--json")
    err_json(r, 5, "parse_error")
    assert "Traceback" not in r.stderr
