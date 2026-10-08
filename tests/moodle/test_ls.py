"""F3 `ilias ls <kurs>` gegen den lokalen Fake-Moodle (127.0.0.1).

Deckt ANFORDERUNGEN.md §3 (F3) und INTERFACE.md §3 ab: Kursauflösung (ID,
Teilstring, exakter Treffer, mehrdeutig, nicht gefunden), Baum aus Abschnitten,
Modulen, Ordnern und Dateien, `--depth`, Sichtbarkeitsmarkierungen und die
Exit-Codes 1/2/3/4/5. Der Token darf nie in Ausgabe oder URL landen (A4).
"""

from __future__ import annotations

import json
import re

import pytest
from acceptance.leak_check import find_secret_in_text

from .conftest import INSTANCE, Harness, RunResult
from .fixtures import COURSE_IDS

PR1 = COURSE_IDS["PR1-WS26"]
MATH1 = COURSE_IDS["MATH1-SS26"]
MATH1_VL = COURSE_IDS["MATH1-SS26-VL"]
SEMINAR = COURSE_IDS["SEM-ARBEIT"]
ILIAS_INSTANCE = "hhn-test"

COURSE_KEYS = {"id", "fullname", "shortname"}
SECTION_KEYS = {"id", "number", "name", "visible", "uservisible", "modules"}
MODULE_KEYS = {"id", "name", "modname", "url", "visible", "uservisible", "availability", "children"}


def login_and(h: Harness) -> None:
    assert h.login("--instance", INSTANCE).exit_code == 0


def ls(h: Harness, kurs: str, *extra: str) -> RunResult:
    return h.run("ls", kurs, "--instance", INSTANCE, *extra)


def ls_json(h: Harness, kurs: str, *extra: str) -> tuple[RunResult, dict]:
    result = ls(h, kurs, "--json", *extra)
    assert result.exit_code == 0, str(result)
    return result, result.json()


def sections_by_id(data: dict) -> dict[int, dict]:
    return {section["id"]: section for section in data["sections"]}


def modules_by_id(section: dict) -> dict[int, dict]:
    return {module["id"]: module for module in section["modules"]}


def walk(nodes: list[dict]):
    """Alle Knoten eines Baums inklusive der verschachtelten Ordner."""
    for node in nodes:
        yield node
        if node.get("type") == "folder":
            yield from walk(node["children"])


def pr1_data(h: Harness, *extra: str) -> dict:
    _, data = ls_json(h, str(PR1), *extra)
    return data


# ------------------------------------------------------------------ Kommando
def test_ls_by_course_id(h: Harness):
    """F3: Kursinhalt über die numerische Kurs-ID."""
    login_and(h)
    result = ls(h, str(PR1))
    assert result.exit_code == 0, str(result)
    out = result.stdout
    assert "Programmieren 1 (WS 2026/27)" in out
    assert "Allgemeines" in out
    assert "Übungsblätter" in out
    assert "blatt01.pdf" in out
    assert "Moodle-Wiki zur Vorlesung" in out
    assert "Probeklausur" in out


def test_ls_by_unique_substring(h: Harness):
    """F3: `<kurs>` darf ein Stück aus Kurzname oder Titel sein (case-insensit)."""
    login_and(h)
    for query in ("programmi", "PROGRAMMIEREN 1 (ws", "pr1-ws26"):
        result = ls(h, query)
        assert result.exit_code == 0, f"{query}: {result}"
        assert "Programmieren 1 (WS 2026/27)" in result.stdout


def test_ls_exact_match_wins_over_substring(h: Harness):
    """F3: exakter Kurzname/Titel schlägt Teilstring-Treffer."""
    login_and(h)
    # "MATH1-SS26" ist exakter Kurzname von 51240 UND Teilstring von 51241
    exact, data = ls_json(h, "MATH1-SS26")
    assert data["course"] == {"id": MATH1, "shortname": "MATH1-SS26", "fullname": "Mathematik 1 (SoSe 2026)"}
    assert exact.exit_code == 0

    _, by_title = ls_json(h, "Mathematik 1 (SoSe 2026)")
    assert by_title["course"]["id"] == MATH1

    ambiguous = ls(h, "MATH1-SS26-VL")
    assert ambiguous.exit_code == 0, str(ambiguous)
    _, vl = ls_json(h, "MATH1-SS26-VL")
    assert vl["course"]["id"] == MATH1_VL


def test_ls_json_shape(h: Harness):
    """F3: ein JSON-Objekt mit instance, lms, course, depth, sections, timestamp."""
    login_and(h)
    result, data = ls_json(h, str(PR1))
    assert result.stdout.strip().startswith("{")
    assert set(data) == {"instance", "lms", "course", "depth", "sections", "timestamp"}, sorted(data)
    assert data["instance"] == INSTANCE and data["lms"] == "moodle"
    assert set(data["course"]) == COURSE_KEYS
    assert data["course"]["id"] == PR1
    assert data["depth"] is None, "ohne --depth ist die Tiefe unbegrenzt (null)"
    for section in data["sections"]:
        assert set(section) == SECTION_KEYS, sorted(section)
        for module in section["modules"]:
            assert set(module) == MODULE_KEYS, sorted(module)


def test_ls_flow_calls_course_contents_with_courseid(h: Harness):
    """Ablauf: Kurs auflösen (Kursliste) -> core_course_get_contents mit courseid."""
    login_and(h)
    before = len(h.world.requests_to("/webservice/rest/server.php"))
    assert ls(h, "PR1-WS26").exit_code == 0
    calls = h.world.requests_to("/webservice/rest/server.php")[before:]
    assert [call.wsfunction for call in calls] == [
        "core_webservice_get_site_info",  # userid
        "core_enrol_get_users_courses",  # Kurs auflösen
        "core_course_get_contents",  # Inhalt
    ], [call.wsfunction for call in calls]
    assert calls[-1].form_value("courseid") == str(PR1)
    assert calls[-1].form_value("moodlewsrestformat") == "json"


# ------------------------------------------------------------------ Baum
def test_ls_tree_structure_from_filepath(h: Harness):
    """F3: `filepath` der Dateien wird zu verschachtelten Ordnern."""
    login_and(h)
    data = pr1_data(h)
    modules = modules_by_id(sections_by_id(data)[502])
    children = modules[9010]["children"]  # Ordner "Übungsblätter"

    root_file = [child for child in children if child["type"] == "file"]
    assert [node["name"] for node in root_file] == ["readme.txt"], children
    assert root_file[0]["path"] == "/"

    folder = next(child for child in children if child["type"] == "folder")
    assert folder["name"] == "Blatt 1"
    assert folder["path"] == "/Blatt 1/"

    subfolder = next(child for child in folder["children"] if child["type"] == "folder")
    assert subfolder["name"] == "Lösungen", "zweite Ordnerebene aus filepath"
    assert subfolder["path"] == "/Blatt 1/Lösungen/"
    files = sorted(node["name"] for node in subfolder["children"] if node["type"] == "file")
    assert files == ["hinweise.pdf", "musterloesung.pdf"]
    bonus = next(child for child in subfolder["children"] if child["type"] == "folder")
    assert bonus["name"] == "Bonus", "dritte Ordnerebene"
    assert bonus["path"] == "/Blatt 1/Lösungen/Bonus/"
    assert [node["name"] for node in bonus["children"]] == ["bonus_loesung.pdf"]

    siblings = sorted(node["name"] for node in folder["children"] if node["type"] == "file")
    assert siblings == ["blatt01.pdf", "blatt02.pdf"]


def test_ls_file_fields(h: Harness):
    """F3: Dateien mit Größe, MIME-Typ, Änderungsdatum und URL."""
    login_and(h)
    data = pr1_data(h)
    modules = modules_by_id(sections_by_id(data)[502])
    file_node = next(node for node in walk(modules[9010]["children"]) if node.get("name") == "blatt01.pdf")
    assert file_node["type"] == "file"
    assert file_node["path"] == "/Blatt 1/"
    assert file_node["size"] == 183456
    assert file_node["mimetype"] == "application/pdf"
    assert file_node["timemodified"] == "2026-10-05T12:00:00+02:00"
    assert file_node["fileurl"].startswith(f"{h.world.base_url}/webservice/pluginfile.php/")
    assert file_node["fileurl"].endswith("blatt01.pdf?forcedownload=1")

    resource_file = modules[9011]["children"][0]
    assert resource_file["name"] == "skript_woche1.pdf"
    assert resource_file["size"] == 1048576


def test_ls_module_types_and_url(h: Harness):
    """F3: Aufgabe/Forum/Test/Seite sind Blätter, `url` zeigt sein Ziel."""
    login_and(h)
    data = pr1_data(h)
    sections = sections_by_id(data)
    general = modules_by_id(sections[501])
    url_module = general[9003]
    assert url_module["modname"] == "url"
    assert url_module["children"] == [
        {"type": "url", "name": "Link", "url": "https://example.org/wiki/pr1"}
    ]

    exams = modules_by_id(sections[503])
    assert exams[9020]["modname"] == "quiz" and exams[9020]["children"] == []
    assert exams[9021]["modname"] == "assign" and exams[9021]["children"] == []
    assert exams[9022]["modname"] == "forum" and exams[9022]["children"] == []
    assert modules_by_id(sections[502])[9012]["modname"] == "page"

    # Der Mensch-Output nennt die Typen
    out = ls(h, str(PR1)).stdout
    for icon_label in ("Aufgabe", "Forum", "Test", "Seite", "Link", "Ordner", "Datei"):
        assert icon_label in out, f"{icon_label} fehlt in der Baum-Anzeige"


def test_ls_label_html_stripped(h: Harness):
    """F3: `label`-Module zeigen kurzen Klartext statt HTML."""
    login_and(h)
    data = pr1_data(h)
    label_module = modules_by_id(sections_by_id(data)[501])[9002]
    assert label_module["modname"] == "label"
    name = label_module["name"]
    assert "<p>" not in name and "<" not in name
    assert name.startswith("Liebe Studierende, herzlich willkommen")
    assert len(name) <= 60, name

    out = ls(h, str(PR1)).stdout
    assert "Liebe Studierende" in out
    assert "<p>" not in out


def test_ls_availability_and_visibility_markers(h: Harness):
    """F3: gesperrte/verborgene Elemente werden gelistet und markiert."""
    login_and(h)
    data = pr1_data(h)
    sections = sections_by_id(data)
    exams = modules_by_id(sections[503])

    restricted = exams[9024]
    assert restricted["uservisible"] is False
    assert restricted["availability"] == (
        "Nicht verfügbar, es sei denn: Du bist in der Gruppe „PoSe 1“ eingeschrieben."
    )

    hidden = exams[9023]
    assert hidden["visible"] is False
    assert hidden["name"] == "[Klausur] Altklausuren"

    archive_section = sections[504]
    assert archive_section["visible"] is False and archive_section["uservisible"] is False

    out = ls(h, str(PR1)).stdout
    assert "[gesperrt]" in out
    assert "[verborgen]" in out
    assert "Nachprüfung" in out, "gesperrte Module werden nicht unterschlagen"
    assert "<div>" not in out, "availabilityinfo kommt als Klartext"


def test_ls_rich_markup_in_names_is_escaped(h: Harness):
    """F3: Servertexte mit Rich-Markup-ähnlichen Klammern dürfen nichts zerstören."""
    login_and(h)
    result = ls(h, str(PR1))
    assert result.exit_code == 0, str(result)
    assert "[Klausur] Altklausuren" in result.stdout
    assert "Traceback" not in result.stderr
    assert "MarkupError" not in result.stderr


def test_ls_empty_section_only_in_json(h: Harness):
    """F3: leere Abschnitte stehen im JSON, nicht im Baum für Menschen."""
    login_and(h)
    result, data = ls_json(h, str(PR1))
    sections = sections_by_id(data)
    assert sections[500]["modules"] == [], "der leere Abschnitt muss im JSON stehen"
    assert sections[500]["number"] == 0
    assert "0. Allgemeines" not in result.stdout, "leere Abschnitte entfallen in der Textausgabe"
    assert "1. Allgemeines" in ls(h, str(PR1)).stdout


def test_ls_course_without_modules(h: Harness):
    """Ein Kurs ohne Inhalt ist kein Fehler."""
    login_and(h)
    result, data = ls_json(h, str(SEMINAR))
    assert data["course"]["id"] == SEMINAR
    assert data["sections"] and all(section["modules"] == [] for section in data["sections"])
    assert result.exit_code == 0
    assert ls(h, str(SEMINAR)).exit_code == 0


# ------------------------------------------------------------------ --depth
@pytest.mark.parametrize("depth", [1, 2, 3, 4, None])
def test_ls_depth_limits_the_json_tree(h: Harness, depth):
    """F3: `--depth` kürzt die Struktur: 1 Abschnitte, 2 Module, 3 Dateien/Ordner,
    jede weitere Stufe eine Ebene tiefer. Vorgabe: unbegrenzt."""
    login_and(h)
    data = pr1_data(h, *(["--depth", str(depth)] if depth else []))
    assert data["depth"] == depth

    if depth == 1:
        assert all(section["modules"] == [] for section in data["sections"])
        return
    sections = sections_by_id(data)
    module = modules_by_id(sections[502])[9010]
    if depth == 2:
        assert module["children"] == []
        assert modules_by_id(sections[503])[9023]["children"] == []
        return

    # Ebene 3: Dateien und Ordner ohne Inhalt
    folder = next(child for child in module["children"] if child["type"] == "folder")
    assert folder["name"] == "Blatt 1"
    assert any(child["type"] == "file" for child in module["children"]), "Dateien ab Ebene 3"
    if depth == 3:
        assert folder["children"] == []
        return

    # Ebene 4: eine Ordnerebene tiefer - die Dateien darin sind noch nicht dabei
    subfolder = next(child for child in folder["children"] if child["type"] == "folder")
    assert subfolder["name"] == "Lösungen"
    if depth == 4:
        assert subfolder["children"] == [], "bei --depth 4 endet die Ausgabe nach dem Ordnernamen"
        return
    # unbegrenzt: vollständige Ordnerstruktur mit Dateien
    assert [node["name"] for node in subfolder["children"] if node["type"] == "file"] == [
        "musterloesung.pdf",
        "hinweise.pdf",
    ]
    bonus = next(child for child in subfolder["children"] if child["type"] == "folder")
    assert bonus["name"] == "Bonus"
    assert [node["name"] for node in bonus["children"]] == ["bonus_loesung.pdf"]


def test_ls_depth_is_shown_in_human_output(h: Harness):
    login_and(h)
    result = ls(h, str(PR1), "--depth", "1")
    assert result.exit_code == 0, str(result)
    assert "Übungsblätter" not in result.stdout, "bei Tiefe 1 kommen keine Module"
    assert "Tiefe 1" in result.stdout


@pytest.mark.parametrize("value", ["0", "-1"])
def test_ls_depth_below_one_is_usage_error(h: Harness, value: str):
    """F3: `--depth < 1` ist ein Aufruffehler (typer: Exit 2)."""
    login_and(h)
    result = ls(h, str(PR1), "--depth", value)
    assert result.exit_code == 2, str(result)
    assert "--depth" in result.stderr


# ------------------------------------------------------------------ Fehler
def test_ls_not_found_exit_1(h: Harness):
    """F3: kein Treffer -> Exit 1 mit error_code course_not_found."""
    login_and(h)
    result = ls(h, "gibtesnicht")
    assert result.exit_code == 1, str(result)
    assert "gibtesnicht" in result.stderr
    data = ls(h, "gibtesnicht", "--json").json()
    assert data["ok"] is False
    assert data["error"]["code"] == "course_not_found"
    assert data["exit_code"] == 1
    assert data["command"] == "ls"


def test_ls_ambiguous_exit_1_with_candidates(h: Harness):
    """F3: mehrere Treffer -> Exit 1, Kandidaten in Meldung und JSON."""
    login_and(h)
    result = ls(h, "mathe")
    assert result.exit_code == 1, str(result)
    assert "MATH1-SS26" in result.stderr and "MATH1-SS26-VL" in result.stderr

    data = ls(h, "mathe", "--json").json()
    assert data["error"]["code"] == "course_ambiguous"
    assert data["exit_code"] == 1
    candidates = data["error"]["candidates"]
    assert [candidate["id"] for candidate in candidates] == [MATH1, MATH1_VL]
    for candidate in candidates:
        assert set(candidate) == {"id", "shortname", "fullname"}
    assert candidates[0]["shortname"] == "MATH1-SS26"
    assert "Mathematik" in candidates[0]["fullname"]


def test_ls_without_token_exit_2(h: Harness):
    """§3: keine gespeicherte Session -> Exit 2 (auch nach logout)."""
    login_and(h)
    assert ls(h, str(PR1)).exit_code == 0
    h.logout("--instance", INSTANCE)
    requests_before = len(h.world.requests)
    result = ls(h, str(PR1))
    assert result.exit_code == 2, str(result)
    assert "login" in result.stderr
    assert len(h.world.requests) == requests_before, "ohne Token wird nicht abgefragt"


def test_ls_without_token_json_exit_2(h: Harness):
    result = ls(h, str(PR1), "--json")
    assert result.exit_code == 2, str(result)
    assert result.json()["error"]["code"] == "not_logged_in"
    assert not h.world.requests, "ohne Token wird nicht abgefragt"


def test_ls_invalid_token_exit_3(h: Harness):
    """A5: invalidtoken -> Exit 3, kein Re-Login."""
    login_and(h)
    h.world.expire_tokens()
    logins_before = len(h.world.requests_to("/login/token.php"))
    result = ls(h, str(PR1), "--json")
    assert result.exit_code == 3, str(result)
    assert result.json()["error"]["code"] == "session_expired"
    assert len(h.world.requests_to("/login/token.php")) == logins_before


def test_ls_server_error_exit_4(h: Harness):
    login_and(h)
    h.world.contents_mode = "server_error"
    result = ls(h, str(PR1), "--json")
    assert result.exit_code == 4, str(result)
    assert result.json()["error"]["code"] == "network_error"


def test_ls_html_response_exit_5(h: Harness):
    login_and(h)
    h.world.contents_mode = "html"
    result = ls(h, str(PR1))
    assert result.exit_code == 5, str(result)


@pytest.mark.parametrize("mode", ["broken", "object"])
def test_ls_unexpected_response_exit_5(h: Harness, mode: str):
    """§3: unerwartete Antwort (fehlende Felder, Objekt statt Liste) -> Exit 5."""
    login_and(h)
    h.world.contents_mode = mode
    result = ls(h, str(PR1), "--json")
    assert result.exit_code == 5, str(result)
    assert result.json()["error"]["code"] == "parse_error"
    assert "Traceback" not in result.stderr


def test_ls_unknown_courseid_is_clear_error(h: Harness):
    """Eine im Server unbekannte courseid wird als Fehler gemeldet, nicht als Absturz."""
    login_and(h)
    h.world.contents = dict(h.world.contents)
    h.world.contents.pop(PR1, None)
    result = ls(h, str(PR1))
    assert result.exit_code == 5, str(result)
    assert "Traceback" not in result.stderr


def test_ls_ilias_backend_not_supported(h: Harness):
    h.write_config(instance=ILIAS_INSTANCE, lms="ilias")
    result = h.run("ls", "51234", "--instance", ILIAS_INSTANCE, "--json")
    assert result.exit_code == 1, str(result)
    data = result.json()
    assert data["error"]["code"] == "not_supported"
    assert "noch nicht implementiert" in data["error"]["message"]
    assert not h.world.requests


# ------------------------------------------------------------------ Token (A4)
def test_ls_token_never_in_output_or_url(h: Harness):
    """A4/N1: der Token steht in keiner Ausgabe und in keiner URL der Ausgabe."""
    login_and(h)
    results = [ls(h, str(PR1)), ls(h, str(PR1), "--json"), ls(h, str(PR1), "--depth", "3", "--json")]
    tokens = list(h.world.tokens)
    assert tokens
    for result in results:
        assert result.exit_code == 0, str(result)
        text = result.stdout + result.stderr
        for token in tokens:
            assert not find_secret_in_text(token, text), "Token in der Ausgabe"
        assert "wstoken" not in text, "Token-Parameter in der Ausgabe"

    _, data = ls_json(h, str(PR1))
    urls = re.findall(r"https?://[^\s\"']+", json.dumps(data, ensure_ascii=False))
    assert urls, "die Ausgabe sollte URLs enthalten (Kurs- und Datei-URLs)"
    for url in urls:
        assert "wstoken" not in url and "token=" not in url, url
    for token in tokens:
        assert not any(token in url for url in urls), "Token in einer URL"


def test_ls_token_sent_in_post_body_only(h: Harness):
    """Der Token wird per POST-Body geschickt, nie als URL-Parameter."""
    login_and(h)
    assert ls(h, str(PR1)).exit_code == 0
    tokens = list(h.world.tokens)
    contents_calls = h.world.calls_to("core_course_get_contents")
    assert contents_calls
    for call in contents_calls:
        assert call.method == "POST"
        assert call.form_value("wstoken") in tokens
        assert call.path == "/webservice/rest/server.php"
        assert call.query == {}
        assert call.form_value("userid") is None, "userid gehört nicht in den Inhaltsaufruf"
