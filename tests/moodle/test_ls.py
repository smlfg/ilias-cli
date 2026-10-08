"""F3 `ilias ls <kurs>` (Moodle): Kursbaum gegen den lokalen Fake-Moodle.

Dekorate: F3 (Baum, Auflösung, Tiefe), INTERFACE.md §3 (Exit-Codes), A4 (Token).
"""

from __future__ import annotations

import json
from datetime import datetime

from .conftest import INSTANCE, Harness, RunResult


def logged_in(h: Harness) -> None:
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)


def assert_json_error(result: RunResult, command: str, exit_code: int, code: str) -> dict:
    data = result.json()
    assert data["ok"] is False, str(result)
    assert data["command"] == command, str(result)
    assert data["exit_code"] == exit_code == result.exit_code, str(result)
    assert data["error"]["code"] == code, str(result)
    return data


def ls_json(h: Harness, *args: str) -> dict:
    result = h.run("ls", *args, "--instance", INSTANCE, "--json")
    assert result.exit_code == 0, str(result)
    data = result.json()
    assert result.stdout.strip().startswith("{"), str(result)
    return data


def count_modules(data: dict) -> int:
    return sum(len(s["modules"]) for s in data["sections"])


# ------------------------------------------------------------------ Auflösung
def test_ls_by_id(h: Harness):
    """F3: `ls 101` findet den Kurs per Id; JSON enthält Kurs + 4 Abschnitte."""
    logged_in(h)
    data = ls_json(h, "101")
    assert data["instance"] == INSTANCE and data["lms"] == "moodle"
    assert data["course"] == {
        "id": 101,
        "shortname": "MATHE-WS26",
        "fullname": "Mathematik 1 (WS 2026/27)",
    }, data["course"]
    assert data["depth"] is None
    assert len(data["sections"]) == 4, data["sections"]
    datetime.fromisoformat(data["timestamp"])


def test_ls_by_unique_substring(h: Harness):
    """F3: eindeutiger Teilstring (case-insensitiv) wählt den Kurs."""
    logged_in(h)
    assert ls_json(h, "programmieren")["course"]["id"] == 201
    assert ls_json(h, "PR1-SS")["course"]["id"] == 201


def test_ls_exact_shortname_wins(h: Harness):
    """F3: exakter Kurzname gewinnt über Teilstring-Treffer (MATHE-WS26 vs. 'mathe')."""
    logged_in(h)
    assert ls_json(h, "MATHE-WS26")["course"]["id"] == 101
    assert ls_json(h, "mathe-ws26")["course"]["id"] == 101


def test_ls_ambiguous(h: Harness):
    """F3: mehrere Treffer -> Exit 1, Kandidaten in Meldung und JSON."""
    logged_in(h)
    result = h.run("ls", "mathe", "--instance", INSTANCE, "--json")
    data = assert_json_error(result, "ls", 1, "course_ambiguous")
    candidates = data["error"]["candidates"]
    assert {c["id"] for c in candidates} == {101, 102}, candidates
    for cand in candidates:
        assert set(cand) == {"id", "shortname", "fullname"}, cand
    assert "101" in data["error"]["message"] and "102" in data["error"]["message"]
    human = h.run("ls", "mathe", "--instance", INSTANCE)
    assert human.exit_code == 1, str(human)
    assert "101" in human.stderr and "102" in human.stderr, str(human)


def test_ls_not_found(h: Harness):
    """F3: kein Treffer -> Exit 1, error_code course_not_found."""
    logged_in(h)
    result = h.run("ls", "gibt-es-nicht", "--instance", INSTANCE, "--json")
    assert assert_json_error(result, "ls", 1, "course_not_found")
    assert h.run("ls", "gibt-es-nicht", "--instance", INSTANCE).exit_code == 1


def test_ls_unknown_id(h: Harness):
    logged_in(h)
    result = h.run("ls", "99999", "--instance", INSTANCE, "--json")
    assert assert_json_error(result, "ls", 1, "course_not_found")


# ------------------------------------------------------------------ Tiefe
def test_ls_depth_shapes(h: Harness):
    """F3: --depth 1/2/3 beschneidet Abschnitte/Bausteine/Dateien (JSON-Knoten zählen)."""
    logged_in(h)
    full = ls_json(h, "101")
    assert count_modules(full) == 9, full  # 3 + 4 + 2 + 0
    d1 = ls_json(h, "101", "--depth", "1")
    assert d1["depth"] == 1
    assert len(d1["sections"]) == 4  # Abschnitte bleiben (leere inkl.)
    assert count_modules(d1) == 0
    d2 = ls_json(h, "101", "--depth", "2")
    assert count_modules(d2) == 9
    assert all(m["children"] == [] for s in d2["sections"] for m in s["modules"])
    d3 = ls_json(h, "101", "--depth", "3")
    assert count_modules(d3) == 9
    folder = next(m for s in d3["sections"] for m in s["modules"] if m["modname"] == "folder")
    names = [c["name"] for c in folder["children"]]
    assert "Blatt 1" in names and "blatt00.pdf" in names, names
    blatt1 = next(c for c in folder["children"] if c["name"] == "Blatt 1")
    assert blatt1["children"] == [], blatt1  # 2. Ordnerebene erst ab --depth 4
    d4 = ls_json(h, "101", "--depth", "4")
    folder4 = next(m for s in d4["sections"] for m in s["modules"] if m["modname"] == "folder")
    blatt1_4 = next(c for c in folder4["children"] if c["name"] == "Blatt 1")
    sub = [c["name"] for c in blatt1_4["children"]]
    assert "Lösungen" in sub and "blatt01.pdf" in sub, sub


def test_ls_depth_zero_is_usage_error(h: Harness):
    """F3: --depth 0 -> Usage-Fehler (Exit 2, Typer-Default)."""
    logged_in(h)
    assert h.run("ls", "101", "--instance", INSTANCE, "--depth", "0").exit_code == 2


# ------------------------------------------------------------------ Baumstruktur
def _module(data: dict, modname: str, name_part: str = "") -> dict:
    for section in data["sections"]:
        for module in section["modules"]:
            if module["modname"] == modname and name_part in module["name"]:
                return module
    raise AssertionError(f"Modul {modname!r}/{name_part!r} nicht gefunden")


def test_ls_nested_folders_from_filepath(h: Harness):
    """F3: filepath-Werte werden zu verschachtelten Ordnern (≥ 2 Ebenen)."""
    logged_in(h)
    data = ls_json(h, "101")
    folder = _module(data, "folder")
    assert folder["name"] == "Übungsblätter"
    top = {c["name"]: c for c in folder["children"]}
    assert set(top) >= {"Blatt 1", "[Klausur] Altklausuren", "blatt00.pdf"}, list(top)
    blatt1 = top["Blatt 1"]
    assert blatt1["type"] == "folder" and blatt1["path"] == "/Blatt 1/"
    sub = {c["name"]: c for c in blatt1["children"]}
    assert "Lösungen" in sub and "blatt01.pdf" in sub, list(sub)
    loesungen = sub["Lösungen"]
    assert loesungen["type"] == "folder" and loesungen["path"] == "/Blatt 1/Lösungen/"
    assert [c["name"] for c in loesungen["children"]] == ["loesung01.pdf"]
    pdf = sub["blatt01.pdf"]
    assert pdf["type"] == "file" and pdf["size"] == 183456
    assert pdf["mimetype"] == "application/pdf"
    assert pdf["timemodified"] == "2026-10-02T02:13:20+02:00"
    assert pdf["fileurl"].startswith(h.world.base_url) and "token" not in pdf["fileurl"].lower()


def test_ls_resource_and_url_modules(h: Harness):
    """F3: resource-Modul zeigt seine Datei, url-Modul das Linkziel."""
    logged_in(h)
    data = ls_json(h, "101")
    resource = _module(data, "resource", "Merkblatt")
    assert len(resource["children"]) == 1
    assert resource["children"][0]["name"] == "merkblatt.pdf"
    link = _module(data, "url", "Skript")
    assert link["children"] == [
        {"type": "url", "name": "Skript-Webseite", "url": "https://example.org/mathe-skript"}
    ], link["children"]


def test_ls_other_modules_are_leaves(h: Harness):
    """F3: assign/forum/quiz/page/choice/label sind Blätter mit Typkennzeichnung."""
    logged_in(h)
    data = ls_json(h, "101")
    for modname in ("assign", "forum", "quiz", "page", "choice", "label"):
        module = _module(data, modname)
        assert module["children"] == [], (modname, module)
    assert _module(data, "forum")["name"] == "Ankündigungen"
    assert _module(data, "quiz", "Grundlagen")["name"] == "Test: Grundlagen"


# ------------------------------------------------------------------ Sichtbarkeit & Text
def test_ls_visibility_markers(h: Harness):
    """F3: uservisible=false -> [gesperrt] + Verfügbarkeit als Klartext; visible=0 -> [verborgen]."""
    logged_in(h)
    data = ls_json(h, "101")
    assign = _module(data, "assign", "Abgabe")
    assert assign["uservisible"] is False
    assert assign["availability"] == "Nicht verfügbar, es sei denn: Es ist nach dem 1. Oktober 2026"
    assert "<" not in assign["availability"] and ">" not in assign["availability"]
    quiz = _module(data, "quiz", "Grundlagen")
    assert quiz["visible"] is False
    human = h.run("ls", "101", "--instance", INSTANCE)
    assert human.exit_code == 0, str(human)
    assert "[gesperrt]" in human.stdout, str(human)
    assert "[verborgen]" in human.stdout, str(human)
    # Der Baum kann lange Zeilen umbrechen: ohne Zeilenumbrüche prüfen.
    flat = human.stdout.replace("\n", " ")
    assert "Es ist nach dem 1. Oktober 2026" in flat, str(human)


def test_ls_label_html_stripped(h: Harness):
    """F3: label-Module zeigen kurzen Klartext (HTML entfernt, max. 60 Zeichen)."""
    logged_in(h)
    data = ls_json(h, "101")
    label = _module(data, "label")
    assert "<" not in label["name"] and ">" not in label["name"], label["name"]
    assert len(label["name"]) <= 61, label["name"]  # 60 + "…"
    assert "Mathematik 1" in label["name"]


def test_ls_human_tree_escapes_markup_and_skips_empty(h: Harness):
    """F3: Rich-Markup in Namen wird maskiert ([Klausur] wörtlich), leere Abschnitte nur im JSON."""
    logged_in(h)
    human = h.run("ls", "101", "--instance", INSTANCE)
    assert human.exit_code == 0, str(human)
    assert "[Klausur] Altklausuren" in human.stdout, str(human)  # kein Crash, wörtlich sichtbar
    assert "Übungsblätter" in human.stdout and "📁" in human.stdout
    assert "merkblatt.pdf" in human.stdout and "179" in human.stdout  # Größe in KB
    assert "💬" in human.stdout and "🔗" in human.stdout  # Typ-Icons
    assert "Abgabe Blatt 1" in human.stdout
    data = ls_json(h, "101")
    empty = [s for s in data["sections"] if s["modules"] == []]
    assert len(empty) == 1 and empty[0]["name"] == "", data["sections"]
    assert empty[0]["id"] == 504


# ------------------------------------------------------------------ Exit-Codes & Geheimnisse
def test_ls_without_token_exit_2(h: Harness):
    result = h.run("ls", "101", "--instance", INSTANCE, "--json")
    from .test_courses import assert_json_error as check

    assert check(result, "ls", 2, "not_logged_in")


def test_ls_invalid_token_exit_3(h: Harness):
    logged_in(h)
    h.world.expire_tokens()
    from .test_courses import assert_json_error as check

    assert check(h.run("ls", "101", "--instance", INSTANCE, "--json"), "ls", 3, "session_expired")


def test_ls_server_error_exit_4(h: Harness):
    logged_in(h)
    h.world.contents_mode = "server_error"
    assert h.run("ls", "101", "--instance", INSTANCE).exit_code == 4


def test_ls_html_exit_5(h: Harness):
    logged_in(h)
    h.world.contents_mode = "html"
    assert h.run("ls", "101", "--instance", INSTANCE).exit_code == 5


def test_ls_token_never_in_output_or_urls(h: Harness):
    """A4: Token nie in stdout/stderr/JSON und nie an fileurl/URL angehängt."""
    logged_in(h)
    tokens = list(h.world.tokens)
    human = h.run("ls", "101", "--instance", INSTANCE)
    as_json = h.run("ls", "101", "--instance", INSTANCE, "--json")
    assert human.exit_code == 0 and as_json.exit_code == 0
    for token in tokens:
        assert token not in human.stdout + human.stderr
        assert token not in as_json.stdout + as_json.stderr
    blob = json.dumps(as_json.json())
    assert "tok-" not in blob and "wstoken" not in blob.lower()

    def _walk(nodes):
        for node in nodes:
            for key in ("fileurl", "url"):
                if node.get(key):
                    assert "token" not in node[key].lower(), node[key]
            _walk(node.get("children", []))

    for section in as_json.json()["sections"]:
        _walk(section["modules"])
        for module in section["modules"]:
            assert module.get("url") is None or "token" not in module["url"].lower()


def test_ls_token_in_post_body_never_in_query(h: Harness):
    """Token im POST-Body, nie im Query-String; Inhalte via core_course_get_contents."""
    logged_in(h)
    assert h.run("ls", "101", "--instance", INSTANCE, "--json").exit_code == 0
    calls = [r for r in h.world.requests_to("/webservice/rest/server.php")]
    assert calls
    for call in calls:
        assert "wstoken" not in call.query
    contents = [c for c in calls if c.form_value("wsfunction") == "core_course_get_contents"]
    assert contents, "core_course_get_contents wurde nicht aufgerufen"
    assert contents[-1].form_value("courseid") == "101"
    assert (contents[-1].form_value("wstoken") or "").startswith("tok-")


def test_ilias_backend_ls_not_supported(h: Harness, monkeypatch):
    """ILIAS-Backend: ls() meldet klar 'noch nicht implementiert' (ohne Netz)."""
    import ilias_core
    from ilias_core.errors import NotSupportedError

    import pytest

    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(h.config_dir))
    service = ilias_core.open_service("hhn")
    with pytest.raises(NotSupportedError, match="für ILIAS noch nicht implementiert"):
        service.backend.course_contents(1)
    with pytest.raises(NotSupportedError, match="für ILIAS noch nicht implementiert"):
        service.ls("101")
    result = h.run("ls", "101", "--instance", "hhn", "--json")
    assert result.exit_code == 1, str(result)
    assert result.json()["error"]["code"] == "not_supported"
