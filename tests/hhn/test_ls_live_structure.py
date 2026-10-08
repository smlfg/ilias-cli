"""F3 `ilias ls` (S7/S8): zusätzliche Tests aus den Live-Befunden vom 08.10. und der Recherche zu ILIAS-Scrapern.

Spec: docs/HHN_2FA_SPEC.md §13.3–§13.9. Nur synthetische Fixtures (tests/hhn/fixtures/, bedient von
tests/hhn/fake_hhn.py), deren Markup der echten HHN-Struktur folgt. Jeder Test nennt den Spec-Punkt.
Eigener Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_ls*.py -q`
"""

from __future__ import annotations

import datetime as dt
import importlib
import unicodedata
from zoneinfo import ZoneInfo

import pytest

from .conftest import HhnHarness
from .fixtures.ls.data import CHAIN_START, NFC_TITLE, NFD_TITLE, ROOT_CATEGORIES
from .helpers import KINDS, err_json, find, kind, names, ok_json, walk

LINK_STYLES = [
    ("https://ilias.example.org/go/crs/900101", "crs", 900101),
    ("https://ilias.example.org/go/fold/900201", "fold", 900201),
    ("https://ilias.example.org/goto.php/fold/900202", "fold", 900202),
    ("https://ilias.example.org/goto.php?target=grp_900105&client_id=testclient", "grp", 900105),
    ("https://ilias.example.org/goto.php?target=file_900301_download", "file", 900301),
    ("https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=900301", "file", 900301),
    ("ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=900401&cmd=calldirectlink", "webr", 900401),
    ("ilias.php?baseClass=ilWikiHandlerGUI&ref_id=900951&cmd=view", "wiki", 900951),
    ("ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=900501&cmd=showOverview", "exc", 900501),
    ("ilias.php?baseClass=ilrepositorygui&cmdClass=ilobjtestgui&ref_id=900601", "tst", 900601),
    ("ilias.php?baseClass=ilrepositorygui&ref_id=900211", None, 900211),  # Typ nur über Icon bestimmbar
    ("#", None, None),
]


@pytest.mark.parametrize("href,typ,ref", LINK_STYLES)
def test_parse_ref_from_all_link_styles(href: str, typ: str | None, ref: int | None):
    """§13.5: ref_id/Typ aus /go/<t>/<id>, goto.php/<t>/<id>, goto.php?target=<t>_<id>[_download] und ref_id= (+Typtabelle)."""
    links = importlib.import_module("ilias_core.ilias_html.links")
    assert links.parse_link(href, "https://ilias.example.org") == (typ, ref)


@pytest.mark.parametrize("text,expected", [
    ("196.37 KB", round(196.37 * 1024)), ("6.8 KB", round(6.8 * 1024)), ("1.5 MB", round(1.5 * 1024**2)),
    ("1,5 MB", round(1.5 * 1024**2)), ("2,25 MB", round(2.25 * 1024**2)), ("820 KB", 820 * 1024),
    ("1 GB", 1024**3), ("1.00 GB", 1024**3), ("512 Bytes", 512), ("pdf", None), ("", None),
    ("25. Sep 2026, 10:12", None),
])
def test_parse_size_dot_and_comma(text: str, expected: int | None):
    """§6.4/§13.4: parse_size akzeptiert Punkt UND Komma als Dezimaltrenner (HHN zeigt z. B. "196.37 KB"), Basis 1024."""
    props = importlib.import_module("ilias_core.ilias_html.props")
    got = props.parse_size(text)
    if expected is None:
        assert got is None
    else:
        assert isinstance(got, int) and abs(got - expected) <= 1, (text, got, expected)


def test_ls_type_table_and_no_followup_for_non_containers(logged_in: HhnHarness):
    """§13.5: explizite Typtabelle; nur fold/grp werden geladen. webr, tst, sess, exc, wiki, crsr und unbekannte
    Typen (Plugin) lösen keinen Folgerequest aus (auch nicht das Ziel des Kurslinks)."""
    n_before = len(logged_in.world.requests)
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    expect = {"Übung 3 --> Lösung (Link)": "url", "Selbsttest Kapitel 1": "test", "Hausaufgabe 1": "exercise",
              "Begriffswiki": "wiki", "Verknüpfung Mathematik-Zusatz": "course_link", "Sitzung 1: Auftakt": "session",
              "Skript Kapitel 1": "file"}
    for name, k in expect.items():
        assert kind(find(data, name)) in KINDS[k], (name, find(data, name))
    assert kind(find(data, "Videoplugin-Objekt")) in {"xvid", "other"}
    refs = set(logged_in.world.requested_refs(n_before))
    for ref in (900401, 900601, 900501, 900951, 900901, 900102, 900971, 900801, 900301):
        assert ref not in refs, (ref, sorted(refs))
    assert not any("expand" in r.query for r in logged_in.world.requests[n_before:])


def test_ls_inline_file_and_course_link(logged_in: HhnHarness):
    """§13.3: Datei mit eigenem Symbol ("Inline Datei", deliver.php statt icon_file.svg) ist eine Datei;
    der Kurslink behält seine eigene ref_id (aus data-list-item-id), nicht die des Zielkurses."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    assert kind(find(data, "Blatt 10")) in KINDS["file"]
    link = find(data, "Verknüpfung Mathematik-Zusatz")
    assert (link.get("ref_id") or link.get("id")) == 900901, link


def test_ls_session_not_expanded_children_null(logged_in: HhnHarness):
    """§13.6: Sitzungen werden nicht aufgeklappt: Knoten mit Typ sess und children = null."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    sess = find(data, "Sitzung 1: Auftakt")
    assert "children" in sess and sess["children"] is None, sess


def test_ls_permission_denied_page_with_category_list_exit1_no_crawl(logged_in: HhnHarness):
    """§13.7: keine Berechtigung -> HHN leitet auf die Magazin-Wurzel um (alert-danger + Kategorienliste).
    Exit 1 permission_denied, die Kategorien werden weder ausgegeben noch geladen."""
    logged_in.world.container_modes[900101] = "forbidden"
    n_before = len(logged_in.world.requests)
    r = logged_in.run("ls", "900101", "--json")
    err_json(r, 1, "permission_denied")
    refs = set(logged_in.world.requested_refs(n_before))
    assert not refs & {ref for ref, _ in ROOT_CATEGORIES}, refs
    assert not any(title in r.stdout for _, title in ROOT_CATEGORIES)


def test_ls_public_page_with_login_link_exit3(logged_in: HhnHarness):
    """§13.7: 200 mit Anmelde-Link (login.php) im Metabar statt Abmelden -> Session weg, Exit 3, kein Crawl."""
    logged_in.world.container_modes[900101] = "public_view"
    n_before = len(logged_in.world.requests)
    err_json(logged_in.run("ls", "900101", "--json"), 3, "session_expired")
    assert not set(logged_in.world.requested_refs(n_before)) & {ref for ref, _ in ROOT_CATEGORIES}


def test_ls_cyclic_folders_terminate(logged_in: HhnHarness):
    """§13.8: visited-Set über ref_id: ein Ordner, der (wieder) auf einen Vorfahren zeigt, wird nicht erneut geladen."""
    logged_in.world.extra_items[900202] = [{"type": "fold", "ref_id": 900201, "title": "Zurück zu Übungsblätter"}]
    n_before = len(logged_in.world.requests)
    r = logged_in.run("ls", "900101", "--json", timeout=30)
    ok_json(r)
    refs = logged_in.world.requested_refs(n_before)
    assert refs.count(900201) <= 2, refs  # /go/fold/<ref> + Redirect-Ziel zählen höchstens einmal je Seite


def test_ls_request_limit_exit5(logged_in: HhnHarness):
    """§13.8: harte Request-Obergrenze (ILIAS_CLI_MAX_REQUESTS, Default 300) -> Exit 5 crawl_limit, keine Teilausgabe."""
    logged_in.world.endless_chain = True
    logged_in.extra_env = {"ILIAS_CLI_MAX_REQUESTS": "40"}
    n_before = len(logged_in.world.requests)
    r = logged_in.run("ls", "900101", "--json", timeout=60)
    data = err_json(r, 5, "crawl_limit")
    assert "sections" not in data
    assert len(logged_in.world.requests) - n_before <= 45
    assert max(logged_in.world.requested_refs(n_before)) < CHAIN_START + 45


def test_ls_titles_nfc_normalized(logged_in: HhnHarness):
    """§6.3/§13.9: Titel in NFC (HTML enthält NFD-Umlaute); Suche ebenfalls normalisiert."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    assert NFD_TITLE != NFC_TITLE
    node = find(data, NFC_TITLE)
    assert unicodedata.is_normalized("NFC", node["name"])
    assert all(unicodedata.is_normalized("NFC", n) for n in names(data) if n)


def test_ls_by_course_number_in_title(logged_in: HhnHarness):
    """§13.1: Kursnummern sind keine ref_ids. Eine Zahl, die keine ref_id einer Mitgliedschaft ist,
    wird als Teilstring im Titel gesucht ("TSTB9.1 Synthesekunde (990041) 2026 WS")."""
    data = ok_json(logged_in.run("ls", "990041", "--json"))
    assert data["course"]["id"] == 900107
    find(data, "Folien Woche 1")


def test_ls_by_course_number_in_description(logged_in: HhnHarness):
    """§13.1: steht die Kursnummer nur in der Beschreibung (HHN: "... SPO5 <nr>"), wird auch dort gesucht."""
    data = ok_json(logged_in.run("ls", "990077", "--json"))
    assert data["course"]["id"] == 900108


def test_ls_unknown_number_not_found_no_root_crawl(logged_in: HhnHarness):
    """§13.1/§13.7: unbekannte Zahl -> Exit 1 course_not_found; die Magazin-Wurzel (ref_id=1) wird nie als Kurs gelesen."""
    n_before = len(logged_in.world.requests)
    err_json(logged_in.run("ls", "900999", "--json"), 1, "course_not_found")
    assert not set(logged_in.world.requested_refs(n_before)) & ({1} | {ref for ref, _ in ROOT_CATEGORIES})


def test_ls_file_dates(logged_in: HhnHarness):
    """§6.4/§13.4: Datum "25. Sep 2026, 10:12" -> ISO 8601 (Europe/Berlin); "Heute, 09:15" -> heutiges Datum oder null."""
    data = ok_json(logged_in.run("ls", "900101", "--json"))
    assert str(find(data, "Skript Kapitel 1").get("timemodified") or "").startswith("2026-09-25T10:12")
    rel = find(data, "Lösung Blatt 2").get("timemodified")
    assert rel is None or str(rel).startswith(dt.datetime.now(tz=ZoneInfo("Europe/Berlin")).date().isoformat()), rel
    assert all(isinstance(n.get("size"), int) for _, n in walk(data["sections"]) if kind(n) == "file")
