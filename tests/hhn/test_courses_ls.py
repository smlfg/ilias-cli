"""F2 `ilias courses` und F3 `ilias ls` für die ILIAS-Instanz `hhn` (HTML-Scraping).

Spec: docs/HHN_2FA_SPEC.md §5-§7. Nur synthetische Fixtures (tests/hhn/fake_hhn.py).
Jeder Test nennt den Spec-Punkt, den er prüft.
"""

from __future__ import annotations

import json

import pytest

from .conftest import HhnHarness
from .fake_hhn import EXPECTED_SEMESTER, LONG_TITLE, MEMBERSHIPS
from .helpers import KINDS, find, kind, max_level, names

NOT_A_COMMAND = ("No such command", "Usage:")  # typer-Fehler zählen nicht als korrektes Verhalten


def ok_json(r) -> dict:
    assert r.exit_code == 0, str(r)
    return json.loads(r.stdout)


def err_json(r, code: int, error_code: str | None = None) -> dict:
    assert r.exit_code == code, str(r)
    assert not any(s in r.stderr for s in NOT_A_COMMAND), f"Befehl fehlt/Usage-Fehler statt Fachfehler:\n{r}"
    data = json.loads(r.stdout)
    assert data.get("ok") is False, data
    if error_code:
        assert data["error"]["code"] == error_code, data
    return data


def ilias_gets(h: HhnHarness) -> list:
    return [r for r in h.world.requests_to("ilias") if r.method == "GET"]


# ======================================================================= F2 courses
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
        assert c["url"].endswith(f"goto.php?target={m['type']}_{m['ref_id']}"), c["url"]
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


# ======================================================================= F3 ls
def test_ls_help(hh: HhnHarness):
    """§6.1: `ls` mit --depth, --json, --instance."""
    r = hh.run("ls", "--help")
    assert r.exit_code == 0, str(r)
    for opt in ("--depth", "--json", "--instance"):
        assert opt in r.stdout


def test_ls_by_ref_id_json_shape(logged_in: HhnHarness):
    """§6.2: course{id,fullname}, sections[] = ILIAS-Blöcke, Objekte darin mit ref_id/Typ/URL."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    assert data["instance"] == "hhn" and data["lms"] == "ilias"
    assert data["course"]["id"] == 900101
    assert data["course"]["fullname"].startswith("Mathematik A")
    assert [s["name"] for s in data["sections"]] == ["Inhalt", "Klausurvorbereitung"]
    for name, k in [("Übungsblätter", "folder"), ("Skript Kapitel 1", "file"), ("Hausaufgabe 1", "exercise"),
                    ("Selbsttest Kapitel 1", "test"), ("Forum für Rückfragen", "forum"),
                    ("Übung 3 --> Lösung (Link)", "url")]:
        node = find(data, name)
        assert kind(node) in KINDS[k], (name, node)
        assert node.get("ref_id") or node.get("id"), node


def test_ls_keeps_server_order(logged_in: HhnHarness):
    """§6.3: Reihenfolge wie in ILIAS (manuelle Sortierung der Lehrenden), nicht umsortieren."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    top = [m["name"] for m in data["sections"][0]["modules"]]
    assert top[:3] == ["Übungsblätter", "Skript Kapitel 1", LONG_TITLE]


def test_ls_nested_folders(logged_in: HhnHarness):
    """§6.2: Ordner werden rekursiv geladen: Übungsblätter -> Lösungen -> Datei + Übung."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    fold = find(data, "Übungsblätter")
    child_names = [c["name"] for c in fold["children"]]
    assert child_names == ["Blatt 10", "Blatt 2", "Lösungen"]
    sub = find(data, "Lösungen")
    assert kind(sub) in KINDS["folder"]
    assert [c["name"] for c in sub["children"]] == ["Lösung Blatt 2", "Abgabe Lösungen"]
    assert kind(find(data, "Abgabe Lösungen")) in KINDS["exercise"]


def test_ls_file_size_and_suffix(logged_in: HhnHarness):
    """§6.4: Größe aus deutschem Format ("1,5 MB", "820 KB", "2,25 MB", "1 GB") in Bytes (±1 %), Dateiendung."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    expected = {"Skript Kapitel 1": 1.5 * 1024**2, LONG_TITLE: 820 * 1024,
                "Lösung Blatt 2": 2.25 * 1024**2, "Klausur Beispieljahr": 1024**3}
    for name, size in expected.items():
        node = find(data, name)
        assert isinstance(node.get("size"), int), node
        assert abs(node["size"] - size) <= size * 0.01, (name, node["size"], size)
        assert node.get("suffix") == "pdf", node


def test_ls_file_download_url_no_session(logged_in: HhnHarness):
    """§6.4: fileurl = ILIAS-Download-Link (goto.php?target=file_<ref>_download), ohne Session-ID/Cookies."""
    r = logged_in.run("ls", "900101", "--json")
    data = ok_json(r)
    node = find(data, "Skript Kapitel 1")
    assert "file_900301_download" in (node.get("fileurl") or ""), node
    for sid in logged_in.world.issued_session_ids:
        assert sid not in r.stdout + r.stderr
    assert "PHPSESSID" not in r.stdout


def test_ls_no_duplicate_entries_and_entities(logged_in: HhnHarness):
    """§6.3 (Lehre aus Moodle-Live-Test): jedes Objekt genau einmal (Dropdown-Links ignorieren),
    HTML-Entities dekodiert (`--&gt;` -> `-->`), lange Titel ungekürzt."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    all_names = names(data)
    assert "Link" not in all_names and "Öffnen" not in all_names
    find(data, "Übung 3 --> Lösung (Link)")  # genau einmal, dekodiert
    find(data, LONG_TITLE)  # ungekürzt
    assert not any("&gt;" in (n or "") or "&amp;" in (n or "") for n in all_names)


def test_ls_offline_and_unknown_types(logged_in: HhnHarness):
    """§6.2: Offline-Objekt bleibt sichtbar mit visible=false; unbekannter Typ (Plugin xvid) -> eigener Typ, kein Absturz."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    assert find(data, "Noch nicht freigegeben")["visible"] is False
    assert find(data, "Skript Kapitel 1")["visible"] is True
    plugin = find(data, "Videoplugin-Objekt")
    assert kind(plugin) in {"xvid", "other"}, plugin


@pytest.mark.parametrize("depth,max_lvl", [(1, 1), (2, 2), (3, 3), (4, 4)])
def test_ls_depth(logged_in: HhnHarness, depth: int, max_lvl: int):
    """§6.1: --depth 1 = Abschnitte, 2 = +Objekte, 3 = +erste Ordnerebene, 4 = +Unterordner."""
    data = ok_json(logged_in.run("ls", "900101", "--depth", str(depth), "--json"))
    assert data["depth"] == depth
    assert max_level(data) == max_lvl, names(data)


def test_ls_depth_limits_requests(logged_in: HhnHarness):
    """§6.1/N2: --depth 2 lädt keine Ordnerseiten (sparsam crawlen)."""
    n_before = len(logged_in.world.requests)
    ok_json(logged_in.run("ls", "900101", "--depth", "2", "--json"))
    refs = [r.query.get("ref_id", [""])[0] for r in logged_in.world.requests[n_before:]]
    assert "900201" not in refs and "900202" not in refs, refs


def test_ls_human_tree_escapes_markup(logged_in: HhnHarness):
    """§6.5: Baum für Menschen; `[Klausur]` erscheint wörtlich (rich-Markup escapen)."""
    r = logged_in.run("ls", "900101")
    assert r.exit_code == 0, str(r)
    assert "[Klausur] Altklausuren" in r.stdout
    assert "Lösung Blatt 2" in r.stdout
    assert "MB" in r.stdout  # Größenangabe


def test_ls_by_unique_substring(logged_in: HhnHarness):
    """§6.1: Teilstring (case-insensitiv) eindeutig -> dieser Kurs."""
    data = ok_json(logged_in.run("ls", "fantasie", "--json"))
    assert data["course"]["id"] == 900103
    assert sum(len(s.get("modules", [])) for s in data["sections"]) == 0  # leerer Kurs ist ok


def test_ls_group_supported(logged_in: HhnHarness):
    """§6.1: Gruppen (grp) gehen wie Kurse."""
    data = ok_json(logged_in.run("ls", "Lerngruppe", "--json"))
    assert data["course"]["id"] == 900105
    find(data, "Notizen der Gruppe")


def test_ls_ambiguous_exit1_candidates(logged_in: HhnHarness):
    """§6.1: "mathe" passt auf zwei Kurse -> Exit 1, course_ambiguous, Kandidaten im JSON."""
    data = err_json(logged_in.run("ls", "mathe", "--json"), 1, "course_ambiguous")
    ids = {c["id"] for c in data["error"]["candidates"]}
    assert ids == {900101, 900102}


def test_ls_not_found_exit1(logged_in: HhnHarness):
    """§6.1: kein Treffer -> Exit 1, course_not_found."""
    err_json(logged_in.run("ls", "zzzz-nichts", "--json"), 1, "course_not_found")


def test_ls_not_logged_in_exit2(hh: HhnHarness):
    err_json(hh.run("ls", "900101", "--json"), 2, "not_logged_in")


def test_ls_session_expires_mid_crawl_exit3(logged_in: HhnHarness):
    """§4.4: Login-Redirect auf einer Unterordner-Seite -> Exit 3 (keine Teilausgabe als Erfolg)."""
    logged_in.world.container_modes[900202] = "login_redirect"
    err_json(logged_in.run("ls", "900101", "--json"), 3, "session_expired")


def test_ls_folder_500_exit4(logged_in: HhnHarness):
    logged_in.world.container_modes[900201] = "error500"
    err_json(logged_in.run("ls", "900101", "--json"), 4, "network_error")


def test_ls_garbage_course_page_exit5(logged_in: HhnHarness):
    """§7: Kursseite ohne Container-Struktur und ohne Leer-Hinweis -> Exit 5."""
    logged_in.world.container_modes[900101] = "garbage"
    r = logged_in.run("ls", "900101", "--json")
    err_json(r, 5, "parse_error")
    assert "Traceback" not in r.stderr
