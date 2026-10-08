"""F3 `ilias ls` für die ILIAS-Instanz `hhn` (HTML-Scraping), Bau-Schritte S7/S8.

Spec: docs/HHN_2FA_SPEC.md §6, §7. Nur synthetische Fixtures (tests/hhn/fixtures/, bedient von
tests/hhn/fake_hhn.py), deren Markup der echten HHN-Struktur folgt. Jeder Test nennt den Spec-Punkt.
Eigener Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_ls*.py -q`
"""

from __future__ import annotations

import pytest

from .conftest import HhnHarness
from .fixtures.ls.data import LONG_TITLE, NFC_TITLE
from .helpers import KINDS, err_json, find, kind, max_level, names, ok_json, ref_ids


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
    # §13.3: Objektblöcke (itgr) und Restblock "Inhalt" in Seitenreihenfolge
    assert [s["name"] for s in data["sections"]] == ["Klausurvorbereitung", "Inhalt", "Sitzungen"]
    for name, k in [("Übungsblätter", "folder"), ("Skript Kapitel 1", "file"), ("Hausaufgabe 1", "exercise"),
                    ("Selbsttest Kapitel 1", "test"), ("Forum für Rückfragen", "forum"),
                    ("Übung 3 --> Lösung (Link)", "url")]:
        node = find(data, name)
        assert kind(node) in KINDS[k], (name, node)
        assert node.get("ref_id") or node.get("id"), node


def test_ls_keeps_server_order(logged_in: HhnHarness):
    """§6.3: Reihenfolge wie in ILIAS (manuelle Sortierung der Lehrenden), nicht umsortieren."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    inhalt = next(s for s in data["sections"] if s["name"] == "Inhalt")
    top = [m["name"] for m in inhalt["modules"]]
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
    """§6.4/§13.4: Größe mit Punkt (HHN: "203.45 KB", "1.5 MB") oder Komma ("2,25 MB") in Bytes (±1 %),
    Endung aus der 1. Eigenschaft; "Version: 2" zwischen den Eigenschaften stört nicht."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    expected = {"Skript Kapitel 1": (1.5 * 1024**2, "pdf"), LONG_TITLE: (820 * 1024, "pdf"),
                "Blatt 10": (203.45 * 1024, "pdf"), "Lösung Blatt 2": (2.25 * 1024**2, "pdf"),
                "Klausur Beispieljahr": (1024**3, "pdf"), NFC_TITLE: (6.8 * 1024, "html")}
    for name, (size, suffix) in expected.items():
        node = find(data, name)
        assert isinstance(node.get("size"), int), node
        assert abs(node["size"] - size) <= size * 0.01, (name, node["size"], size)
        assert node.get("suffix") == suffix, node


def test_ls_file_download_url_no_session(logged_in: HhnHarness):
    """§6.4/§13.4: fileurl = ILIAS-Download-Link (HHN: ...cmd=sendfile&ref_id=<ref>), ohne Session-ID/Cookies."""
    r = logged_in.run("ls", "900101", "--json")
    data = ok_json(r)
    node = find(data, "Skript Kapitel 1")
    url = node.get("fileurl") or ""
    assert ("cmd=sendfile" in url and "ref_id=900301" in url) or "file_900301_download" in url, node
    assert url.startswith(logged_in.world.ilias_base), url
    for sid in logged_in.world.issued_session_ids:
        assert sid not in r.stdout + r.stderr
    assert "PHPSESSID" not in r.stdout


def test_ls_no_duplicate_entries_and_entities(logged_in: HhnHarness):
    """§6.3/§13.3 (Lehre aus Moodle-Live-Test): jedes Objekt genau einmal (Dropdown-Links, `href="#"` und
    `a.glyph` neben dem Titel ignorieren, ein Eintrag pro ref_id), HTML-Entities dekodiert, lange Titel ungekürzt."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    all_names = names(data)
    for label in ("Download", "Info", "Information", "Zu Favoriten hinzufügen", "Notizen", "Tags setzen", "", None):
        assert label not in all_names, (label, all_names)
    refs = ref_ids(data)
    assert len(refs) == len(set(refs)), refs
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
    refs = logged_in.world.requested_refs(n_before)
    assert 900201 not in refs and 900202 not in refs and 900203 not in refs, refs


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
