"""F3 `ilias ls <kurs>`: Kursbaum gegen den lokalen Fake-Moodle (127.0.0.1).

Prüft Kursauflösung (ID/Teilstring/exakt/mehrdeutig), Baumaufbau aus `filepath`,
`--depth`, Sichtbarkeitsmarker, Label-Bereinigung, Rich-Markup-Escaping und die
Exit-Codes. Es wird nie ein echter Server kontaktiert.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from acceptance.leak_check import find_secret_in_text

from ilias_core import (
    Course,
    CourseAmbiguousError,
    CourseNotFoundError,
    resolve_course,
)

from .conftest import INSTANCE, Harness, RunResult

COURSE_ID = 101


def assert_logged_in(h: Harness) -> RunResult:
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    return result


def assert_error(result: RunResult, command: str, exit_code: int, code: str) -> dict:
    data = result.json()
    assert data["ok"] is False, str(result)
    assert data["command"] == command, str(result)
    assert data["exit_code"] == exit_code == result.exit_code, str(result)
    assert data["error"]["code"] == code, str(result)
    return data


def ls_json(h: Harness, kurs: str, *extra: str) -> dict:
    result = h.run("ls", kurs, "--instance", INSTANCE, "--json", *extra)
    assert result.exit_code == 0, str(result)
    return result.json()


def find_module(data: dict, module_id: int) -> dict:
    for section in data["sections"]:
        for module in section["modules"]:
            if module["id"] == module_id:
                return module
    raise AssertionError(f"Modul {module_id} nicht gefunden")


# ------------------------------------------------------------------ Auflösung (pure)
def _course(course_id: int, shortname: str, fullname: str) -> Course:
    return Course(id=course_id, shortname=shortname, fullname=fullname)


def test_resolve_by_id():
    courses = [_course(7, "X", "Irgendwas"), _course(8, "Y", "Anderes")]
    assert resolve_course(courses, "8").id == 8


def test_resolve_exact_shortname_wins_over_substring():
    """Ein exakter Kurzname schlägt einen bloßen Teilstring."""
    courses = [_course(1, "MA2", "Mathematik 2"), _course(2, "MA2-ALT", "Mathematik 2 Altklausuren")]
    assert resolve_course(courses, "ma2").id == 1


def test_resolve_unique_substring():
    courses = [_course(1, "PR1-WS26", "Programmieren 1")]
    assert resolve_course(courses, "programmieren").id == 1


def test_resolve_not_found():
    with pytest.raises(CourseNotFoundError):
        resolve_course([_course(1, "X", "Y")], "gibtsnicht")


def test_resolve_ambiguous_carries_candidates():
    courses = [_course(1, "A", "Mathe A"), _course(2, "B", "Mathe B")]
    with pytest.raises(CourseAmbiguousError) as excinfo:
        resolve_course(courses, "mathe")
    assert {candidate["id"] for candidate in excinfo.value.candidates} == {1, 2}


# ------------------------------------------------------------------ Auflösung (CLI)
def test_ls_by_id(h: Harness):
    assert_logged_in(h)
    result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    for needle in ("Programmieren 1", "Allgemeines", "Übungsblätter", "Übung 1"):
        assert needle in result.stdout, str(result)


def test_ls_by_unique_substring(h: Harness):
    assert_logged_in(h)
    result = h.run("ls", "PR1", "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert "Programmieren 1" in result.stdout


def test_ls_ambiguous_exit_1(h: Harness):
    assert_logged_in(h)
    result = h.run("ls", "mathe", "--instance", INSTANCE)
    assert result.exit_code == 1, str(result)
    assert "Mehrere" in result.stderr, str(result)
    assert "MA1-SS26" in result.stderr and "MA2-WS26" in result.stderr, str(result)


def test_ls_ambiguous_json_candidates(h: Harness):
    assert_logged_in(h)
    result = h.run("ls", "mathe", "--instance", INSTANCE, "--json")
    data = assert_error(result, "ls", 1, "course_ambiguous")
    candidates = data["error"]["candidates"]
    assert {candidate["id"] for candidate in candidates} == {102, 103}
    for candidate in candidates:
        assert set(candidate) == {"id", "fullname", "shortname"}
    assert "mathe" in data["error"]["message"]


def test_ls_not_found_exit_1(h: Harness):
    assert_logged_in(h)
    result = h.run("ls", "gibtsnicht", "--instance", INSTANCE)
    assert result.exit_code == 1, str(result)
    assert "Kein Kurs" in result.stderr, str(result)


def test_ls_not_found_json(h: Harness):
    assert_logged_in(h)
    result = h.run("ls", "gibtsnicht", "--instance", INSTANCE, "--json")
    assert_error(result, "ls", 1, "course_not_found")


# ------------------------------------------------------------------ JSON-Form
def test_ls_json_shape(h: Harness):
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID))
    assert set(data) == {"instance", "lms", "course", "depth", "sections", "timestamp"}
    assert data["instance"] == INSTANCE and data["lms"] == "moodle"
    assert data["depth"] is None
    assert data["course"] == {
        "id": COURSE_ID,
        "fullname": "Programmieren 1 (WS 2026/27)",
        "shortname": "PR1-WS26",
    }
    assert datetime.fromisoformat(data["timestamp"]).tzinfo is not None
    assert [section["number"] for section in data["sections"]] == [0, 1, 2, 3]
    for section in data["sections"]:
        assert set(section) == {"id", "number", "name", "visible", "uservisible", "modules"}
        for module in section["modules"]:
            assert set(module) == {
                "id",
                "name",
                "modname",
                "url",
                "visible",
                "uservisible",
                "availability",
                "children",
            }


def test_ls_empty_section_present_in_json(h: Harness):
    """Leere Abschnitte dürfen im Menschen-Text fehlen, müssen aber im JSON stehen."""
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID))
    empty = next(section for section in data["sections"] if section["id"] == 503)
    assert empty["modules"] == [] and empty["name"] == ""


# ------------------------------------------------------------------ Baum & filepath
def test_ls_nested_folder_structure(h: Harness):
    """`filepath` wird zu verschachtelten Ordnern (>= 2 Ebenen)."""
    assert_logged_in(h)
    module = find_module(ls_json(h, str(COURSE_ID)), 9001)
    folders = {child["name"]: child for child in module["children"] if child["type"] == "folder"}
    assert set(folders) == {"Blatt 1", "Blatt 2"}, module["children"]
    blatt1 = folders["Blatt 1"]
    assert blatt1["path"] == "/Blatt 1/"
    loesungen = next(child for child in blatt1["children"] if child["type"] == "folder")
    assert loesungen["name"] == "Lösungen" and loesungen["path"] == "/Blatt 1/Lösungen/"
    assert [f["name"] for f in loesungen["children"]] == ["loesung1.md"]
    root_files = [c["name"] for c in module["children"] if c["type"] == "file"]
    assert root_files == ["blatt01.pdf"]


def test_ls_file_fields(h: Harness):
    assert_logged_in(h)
    module = find_module(ls_json(h, str(COURSE_ID)), 9010)
    file_node = module["children"][0]
    assert file_node["type"] == "file"
    assert file_node["name"] == "kapitel1.pdf"
    assert file_node["size"] == 1048576
    assert file_node["mimetype"] == "application/pdf"
    assert datetime.fromisoformat(file_node["timemodified"]).tzinfo is not None
    assert "token" not in file_node["fileurl"]


def test_ls_url_module(h: Harness):
    assert_logged_in(h)
    module = find_module(ls_json(h, str(COURSE_ID)), 9002)
    assert module["modname"] == "url"
    assert module["children"] == [{"type": "url", "name": "Moodle-Doku", "url": "https://docs.moodle.org/"}]


# ------------------------------------------------------------------ --depth
def test_ls_depth_1_only_sections(h: Harness):
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID), "--depth", "1")
    assert data["depth"] == 1
    assert len(data["sections"]) == 4
    assert all(section["modules"] == [] for section in data["sections"])


def test_ls_depth_2_modules_without_children(h: Harness):
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID), "--depth", "2")
    assert data["depth"] == 2
    modules = [m for section in data["sections"] for m in section["modules"]]
    assert len(modules) == 10
    assert all(module["children"] == [] for module in modules)


def test_ls_depth_3_first_folder_level(h: Harness):
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID), "--depth", "3")
    folder = find_module(data, 9001)
    assert [child["type"] for child in folder["children"]] == ["folder", "folder", "file"]
    # Die erste Ordnerebene ist da, aber noch leer (nächste Ebene erst bei depth 4)
    assert all(child["children"] == [] for child in folder["children"] if child["type"] == "folder")


def test_ls_depth_4_descends_one_more_level(h: Harness):
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID), "--depth", "4")
    folder = find_module(data, 9001)
    blatt1 = next(child for child in folder["children"] if child["name"] == "Blatt 1")
    assert [child["name"] for child in blatt1["children"]] == ["Lösungen", "aufgabe1.pdf"]
    loesungen = next(child for child in blatt1["children"] if child["type"] == "folder")
    assert loesungen["children"] == []


def test_ls_depth_5_reaches_deepest_file(h: Harness):
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID), "--depth", "5")
    folder = find_module(data, 9001)
    blatt1 = next(child for child in folder["children"] if child["name"] == "Blatt 1")
    loesungen = next(child for child in blatt1["children"] if child["type"] == "folder")
    assert [f["name"] for f in loesungen["children"]] == ["loesung1.md"]


def test_ls_depth_below_one_is_usage_error(h: Harness):
    """N < 1 -> Usage-Fehler (Exit 2, typer-Default)."""
    assert_logged_in(h)
    result = h.run("ls", str(COURSE_ID), "--depth", "0", "--instance", INSTANCE)
    assert result.exit_code == 2, str(result)


# ------------------------------------------------------------------ Sichtbarkeit & Label
def test_ls_visibility_markers_in_json(h: Harness):
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID))
    choice = find_module(data, 9022)
    assert choice["uservisible"] is False
    assert "Nicht verfügbar" in choice["availability"]
    assert "<div>" not in choice["availability"]
    quiz = find_module(data, 9021)
    assert quiz["visible"] is False


def test_ls_visibility_markers_in_human_output(h: Harness):
    assert_logged_in(h)
    result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert "[gesperrt]" in result.stdout, str(result)
    assert "[verborgen]" in result.stdout, str(result)


def test_ls_label_html_stripped(h: Harness):
    assert_logged_in(h)
    module = find_module(ls_json(h, str(COURSE_ID)), 9003)
    assert module["modname"] == "label"
    assert "<" not in module["name"] and "strong" not in module["name"]
    assert module["name"].startswith("Willkommen im Kurs")


def test_ls_rich_markup_in_names_is_literal(h: Harness):
    """Namen wie `[Klausur] Altklausuren` dürfen Rich nicht als Markup deuten."""
    assert_logged_in(h)
    data = ls_json(h, str(COURSE_ID))
    assert find_module(data, 9020)["name"] == "[Klausur] Altklausuren"
    result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert "[Klausur] Altklausuren" in result.stdout, str(result)


# ------------------------------------------------------------------ Fehlerfälle
def test_ls_without_token_exit_2(h: Harness):
    result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    assert result.exit_code == 2, str(result)
    assert h.world.requests == [], "Server ohne Session kontaktiert"


def test_ls_invalid_token_exit_3(h: Harness):
    assert_logged_in(h)
    h.world.expire_tokens()
    result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    assert result.exit_code == 3, str(result)


def test_ls_server_error_exit_4(h: Harness):
    assert_logged_in(h)
    h.world.rest_mode = "server_error"
    result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    assert result.exit_code == 4, str(result)


def test_ls_html_exit_5(h: Harness):
    assert_logged_in(h)
    h.world.rest_mode = "html"
    result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    assert result.exit_code == 5, str(result)


# ------------------------------------------------------------------ Sicherheit
def test_ls_token_never_in_output_or_url(h: Harness):
    """A4/F3: Token nie in der Ausgabe und nie an fileurl/URLs angehängt."""
    assert_logged_in(h)
    token = next(iter(h.world.tokens))
    for extra in ((), ("--json",)):
        result = h.run("ls", str(COURSE_ID), "--instance", INSTANCE, *extra)
        assert result.exit_code == 0, str(result)
        assert token not in result.stdout + result.stderr
        assert not find_secret_in_text(token, result.stdout + result.stderr)
    data = ls_json(h, str(COURSE_ID))
    for section in data["sections"]:
        for module in section["modules"]:
            assert token not in (module["url"] or "")
            for child in module["children"]:
                assert token not in child.get("fileurl", "")
                assert token not in child.get("url", "")
    for request in h.world.requests:
        assert token not in request.path
        assert all(token not in value for values in request.query.values() for value in values)


def test_ls_token_in_post_body_not_query(h: Harness):
    assert_logged_in(h)
    h.run("ls", str(COURSE_ID), "--instance", INSTANCE)
    contents = [
        r
        for r in h.world.requests_to("/webservice/rest/server.php")
        if r.form_value("wsfunction") == "core_course_get_contents"
    ]
    assert contents, "core_course_get_contents wurde nicht aufgerufen"
    for request in contents:
        assert (request.form_value("wstoken") or "").startswith("tok-")
        assert request.form_value("courseid") == str(COURSE_ID)
        assert "wstoken" not in request.query
