"""F3 `ilias ls` gegen den lokalen Fake-Moodle."""

from __future__ import annotations

from .conftest import INSTANCE, Harness


def _logged_in(h: Harness):
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    return result


def _run_json(h: Harness, *args: str):
    result = h.run("ls", *args, "--instance", INSTANCE, "--json")
    assert result.exit_code == 0, str(result)
    return result.json()


def _module_names(sections):
    names = []
    for s in sections:
        for m in s["modules"]:
            names.append(m["name"])
    return names


# ------------------------------------------------------------------ Auflösung
def test_ls_by_id(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234")
    assert data["course"]["id"] == 1234
    assert data["course"]["fullname"] == "Mathe 1 (WS 2026/27)"
    assert data["lms"] == "moodle"
    assert data["depth"] is None
    assert "timestamp" in data


def test_ls_by_unique_substring(h: Harness):
    _logged_in(h)
    data = _run_json(h, "programmieren")
    assert data["course"]["id"] == 1236


def test_ls_exact_shortname_wins_over_substring(h: Harness):
    _logged_in(h)
    # "MA2-SS27" ist exakter Shortname von 1235; Teilstring "ma2" würde nichts
    # Eindeutiges finden ohne Exaktheits-Vorrang.
    data = _run_json(h, "MA2-SS27")
    assert data["course"]["id"] == 1235


def test_ls_ambiguous_lists_candidates(h: Harness):
    _logged_in(h)
    result = h.run("ls", "mathe", "--instance", INSTANCE, "--json")
    assert result.exit_code == 1, str(result)
    data = result.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "course_ambiguous"
    candidates = data["error"]["candidates"]
    assert {c["id"] for c in candidates} == {1234, 1235}
    for c in candidates:
        assert set(c) == {"id", "shortname", "fullname"}
    assert "MA1-WS26" in result.stderr or "MA1-WS26" in result.stdout


def test_ls_not_found(h: Harness):
    _logged_in(h)
    result = h.run("ls", "gibtsnicht", "--instance", INSTANCE, "--json")
    assert result.exit_code == 1, str(result)
    assert result.json()["error"]["code"] == "course_not_found"


# ------------------------------------------------------------------ Baum / Depth
def _section_count(data):
    return len(data["sections"])


def test_ls_depth_1_sections_only(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234", "--depth", "1")
    assert data["depth"] == 1
    assert _section_count(data) == 5
    for section in data["sections"]:
        assert section["modules"] == []


def test_ls_depth_2_has_modules_no_children(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234", "--depth", "2")
    assert data["depth"] == 2
    names = _module_names(data["sections"])
    assert "Übungsblätter" in names
    for section in data["sections"]:
        for module in section["modules"]:
            assert module["children"] == []


def test_ls_depth_3_first_folder_level(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234", "--depth", "3")
    folder = _find_module(data, "Übungsblätter")
    children = folder["children"]
    names = [c["name"] for c in children]
    assert "Blatt 1" in names and "Blatt 2" in names
    blatt1 = next(c for c in children if c["name"] == "Blatt 1")
    assert blatt1["type"] == "folder"
    assert blatt1["path"] == "/Blatt 1/"
    # Ebene 2 ist abgeschnitten
    assert blatt1["children"] == []
    # Dateien auf der ersten Ebene
    resource = _find_module(data, "Skript.pdf")
    assert resource["children"][0]["type"] == "file"


def test_ls_unlimited_shows_nested_folders(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234")
    folder = _find_module(data, "Übungsblätter")
    blatt1 = next(c for c in folder["children"] if c["name"] == "Blatt 1")
    names = [c["name"] for c in blatt1["children"]]
    assert "blatt01.pdf" in names
    assert "Lösungen" in names
    loes = next(c for c in blatt1["children"] if c["name"] == "Lösungen")
    assert loes["type"] == "folder"
    assert loes["path"] == "/Blatt 1/Lösungen/"
    inner = loes["children"][0]
    assert inner["type"] == "file"
    assert inner["name"] == "blatt01_lsg.pdf"
    assert inner["size"] == 95432
    assert inner["mimetype"] == "application/pdf"
    assert inner["timemodified"].startswith("2026-10-15")
    assert inner["fileurl"].startswith(h.world.base_url)
    assert "tok-" not in inner["fileurl"]


def _find_module(data, name):
    for section in data["sections"]:
        for module in section["modules"]:
            if module["name"] == name:
                return module
    raise AssertionError(f"Modul {name!r} nicht gefunden")


def test_ls_depth_4_one_more_folder_level(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234", "--depth", "4")
    folder = _find_module(data, "Übungsblätter")
    blatt1 = next(c for c in folder["children"] if c["name"] == "Blatt 1")
    loes = next(c for c in blatt1["children"] if c["name"] == "Lösungen")
    assert loes["children"] == []


def test_ls_depth_invalid(h: Harness):
    _logged_in(h)
    result = h.run("ls", "1234", "--instance", INSTANCE, "--depth", "0")
    assert result.exit_code == 2, str(result)


def test_ls_uservisible_false_marker(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234")
    locked = _find_module(data, "Abschlussprojekt")
    assert locked["uservisible"] is False
    assert locked["availability"] == "Nicht verfügbar, es sei denn: die vorherige Aktivität ist abgeschlossen"
    assert "<div>" not in locked["availability"]
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert "[gesperrt]" in result.stdout


def test_ls_hidden_module_marker(h: Harness):
    _logged_in(h)
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert "[verborgen]" in result.stdout
    data = _run_json(h, "1234")
    quiz = _find_module(data, "Probeklausur")
    assert quiz["visible"] is False


def test_ls_label_html_stripped(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234")
    label = next(m for m in (mm for s in data["sections"] for mm in s["modules"]) if m["modname"] == "label")
    assert label["name"].startswith("Herzlich willkommen")
    assert label["modname"] == "label"
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert "<p>" not in result.stdout
    assert "Herzlich willkommen" in result.stdout


def test_ls_markup_in_names_is_escaped(h: Harness):
    _logged_in(h)
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    assert "[Klausur] Altklausuren" in result.stdout  # literal sichtbar, kein Crash


def test_ls_url_module_target(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234")
    url_mod = _find_module(data, "Kursseite")
    assert url_mod["modname"] == "url"
    assert url_mod["children"][0]["type"] == "url"
    assert url_mod["children"][0]["url"] == "https://www.example.edu/fh"


def test_ls_token_never_in_output(h: Harness):
    _logged_in(h)
    for args in [("1234", "--json"), ("1234",), ("1238", "--json")]:
        result = h.run("ls", *args, "--instance", INSTANCE)
        for token in h.world.tokens:
            assert token not in result.stdout, args
            assert token not in result.stderr, args
    for req in h.world.requests:
        for values in req.query.values():
            assert all("tok-" not in v for v in values)


def test_ls_empty_section_present_in_json_skipped_in_human(h: Harness):
    _logged_in(h)
    data = _run_json(h, "1234")
    assert _section_count(data) == 5
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert "Prüfungsorganisation" in result.stdout


def test_ls_course_not_found_exit_2_without_token(h: Harness):
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert result.exit_code == 2, str(result)


def test_ls_invalidtoken_exit_3(h: Harness):
    _logged_in(h)
    h.world.expire_tokens()
    result = h.run("ls", "1234", "--instance", INSTANCE, "--json")
    assert result.exit_code == 3, str(result)


def test_ls_server_error_exit_4(h: Harness):
    _logged_in(h)
    h.world.rest_mode = "server_error"
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert result.exit_code == 4, str(result)


def test_ls_html_exit_5(h: Harness):
    _logged_in(h)
    h.world.rest_mode = "html"
    result = h.run("ls", "1234", "--instance", INSTANCE)
    assert result.exit_code == 5, str(result)


def test_ls_ilias_backend_not_supported(h: Harness):
    h.write_config(base_url="https://ilias.example.org", lms="ilias")
    result = h.run("ls", "Mathe")
    assert result.exit_code == 1, str(result)
    assert "nicht implementiert" in result.stderr
    assert "Traceback" not in result.stderr
