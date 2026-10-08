"""F2 `ilias courses` (Moodle): Kursliste gegen den lokalen Fake-Moodle.

Dekorate: F2 (eigene Kurse auflisten), INTERFACE.md §3 (Exit-Codes), A4 (Token).
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from ilias_core.errors import NotSupportedError
from ilias_core.timeutil import semester_label, timestamp_to_iso

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


# ------------------------------------------------------------------ Ausgabe
def test_courses_human_table_sorted(h: Harness):
    """F2: Tabelle (ID, Kurzname, Name, Semester), neuestes Semester zuerst, null zuletzt."""
    logged_in(h)
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    for head in ("ID", "Kurzname", "Name", "Semester"):
        assert head in result.stdout, str(result)
    for short in ("MATHE-WS26", "MATHE-UE", "PR1-SS26", "PHYS-ALT"):
        assert short in result.stdout, str(result)
    assert "WiSe 2026/27" in result.stdout, str(result)
    assert "SoSe 2026" in result.stdout, str(result)
    wise = min(result.stdout.index("MATHE-WS26"), result.stdout.index("MATHE-UE"))
    sose = result.stdout.index("PR1-SS26")
    nostart = result.stdout.index("PHYS-ALT")
    assert wise < sose < nostart, str(result)


def test_courses_json_shape(h: Harness):
    """F2: genau ein JSON-Objekt mit instance/lms/count/courses/timestamp."""
    logged_in(h)
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert result.exit_code == 0, str(result)
    data = result.json()
    assert result.stdout.strip().startswith("{"), str(result)
    for key in ("instance", "lms", "count", "courses", "timestamp"):
        assert key in data, sorted(data)
    assert data["instance"] == INSTANCE and data["lms"] == "moodle"
    assert data["count"] == 4 == len(data["courses"])
    datetime.fromisoformat(data["timestamp"])  # N5: ISO 8601 mit Zeitzone
    by_id = {c["id"]: c for c in data["courses"]}
    mathe = by_id[101]
    assert set(mathe) == {
        "id", "fullname", "shortname", "category", "semester",
        "visible", "startdate", "enddate", "url",
    }, sorted(mathe)
    assert mathe["fullname"] == "Mathematik 1 (WS 2026/27)"
    assert mathe["shortname"] == "MATHE-WS26"
    assert mathe["category"] == 17
    assert mathe["semester"] == "WiSe 2026/27"
    assert mathe["visible"] is True
    assert mathe["startdate"] == "2026-10-01T10:00:00+02:00"
    assert mathe["enddate"] == "2027-03-31T23:59:00+02:00"
    assert mathe["url"] == f"{h.world.base_url}/course/view.php?id=101"
    physik = by_id[301]
    assert physik["semester"] is None
    assert physik["startdate"] is None and physik["enddate"] is None
    assert physik["category"] is None
    assert physik["visible"] is False


def test_courses_json_sorted_newest_first(h: Harness):
    """F2: auch im JSON steht das neueste Semester zuerst, null zuletzt."""
    logged_in(h)
    data = h.run("courses", "--instance", INSTANCE, "--json").json()
    assert [c["id"] for c in data["courses"]] == [101, 102, 201, 301], data["courses"]


# ------------------------------------------------------------------ Semester (reine Funktion)
@pytest.mark.parametrize(
    ("startdate", "expected"),
    [
        (1775030400, "SoSe 2026"),  # 2026-04-01 (Berlin)
        (1790805540, "SoSe 2026"),  # 2026-09-30 (letzter SoSe-Tag)
        (1790841600, "WiSe 2026/27"),  # 2026-10-01 (Berlin)
        (1801472400, "WiSe 2026/27"),  # 2027-02-01 (Berlin, Jan–Mär-Fall)
        (1768467600, "WiSe 2025/26"),  # 2026-01-15 (Jan–Mär-Fall)
        (0, None),
        (None, None),
        ("", None),
    ],
)
def test_semester_label(startdate, expected):
    """F2: Semester aus startdate (Europe/Berlin), 0/fehlend -> None."""
    assert semester_label(startdate) == expected


def test_timestamp_to_iso_none_cases():
    assert timestamp_to_iso(0) is None
    assert timestamp_to_iso(None) is None
    assert timestamp_to_iso("1790841600") is None
    assert timestamp_to_iso(1790841600) == "2026-10-01T10:00:00+02:00"


# ------------------------------------------------------------------ Exit-Codes (§3)
def test_courses_without_token_exit_2(h: Harness):
    """§3: kein gespeicherter Token -> Exit 2."""
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 2, str(result)
    as_json = h.run("courses", "--instance", INSTANCE, "--json")
    assert assert_json_error(as_json, "courses", 2, "not_logged_in")


def test_courses_invalid_token_exit_3(h: Harness):
    """§3: invalidtoken -> Exit 3, kein Re-Login."""
    logged_in(h)
    h.world.expire_tokens()
    token_calls = len(h.world.requests_to("/login/token.php"))
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert assert_json_error(result, "courses", 3, "session_expired")
    assert len(h.world.requests_to("/login/token.php")) == token_calls, "Re-Login trotz invalidtoken"


def test_courses_server_error_exit_4(h: Harness):
    """§3: HTTP 5xx -> Exit 4."""
    logged_in(h)
    h.world.courses_mode = "server_error"
    assert h.run("courses", "--instance", INSTANCE).exit_code == 4


def test_courses_html_exit_5(h: Harness):
    """§3: HTML statt JSON -> Exit 5."""
    logged_in(h)
    h.world.courses_mode = "html"
    assert h.run("courses", "--instance", INSTANCE).exit_code == 5


# ------------------------------------------------------------------ Geheimnisse (A1/A4)
def test_token_never_in_output_or_urls(h: Harness):
    """A4: Token nie in stdout/stderr/JSON und nie an eine URL angehängt."""
    logged_in(h)
    tokens = list(h.world.tokens)
    assert tokens
    human = h.run("courses", "--instance", INSTANCE)
    as_json = h.run("courses", "--instance", INSTANCE, "--json")
    assert human.exit_code == 0 and as_json.exit_code == 0
    for token in tokens:
        assert token not in human.stdout + human.stderr, "Token in human-Ausgabe"
        assert token not in as_json.stdout + as_json.stderr, "Token in JSON-Ausgabe"
    data = as_json.json()
    assert "tok-" not in json.dumps(data)
    assert "wstoken" not in json.dumps(data).lower()
    for course in data["courses"]:
        assert "token" not in course["url"].lower(), course["url"]


def test_token_sent_in_post_body_never_in_query_string(h: Harness):
    """Token steht im POST-Body, nie im Query-String (F5 lädt später, nicht hier)."""
    logged_in(h)
    assert h.run("courses", "--instance", INSTANCE, "--json").exit_code == 0
    rest_calls = h.world.requests_to("/webservice/rest/server.php")
    assert rest_calls, "kein REST-Aufruf aufgezeichnet"
    for call in rest_calls:
        assert call.method == "POST"
        assert "wstoken" not in call.query, f"Token im Query-String: {call.query}"
    for wsfunction in ("core_webservice_get_site_info", "core_enrol_get_users_courses"):
        matches = [c for c in rest_calls if c.form_value("wsfunction") == wsfunction]
        assert matches, f"{wsfunction} wurde nicht aufgerufen"
        assert (matches[-1].form_value("wstoken") or "").startswith("tok-")
    enrol = [c for c in rest_calls if c.form_value("wsfunction") == "core_enrol_get_users_courses"][-1]
    assert enrol.form_value("userid") == "4711"


# ------------------------------------------------------------------ ILIAS-Backend
def test_ilias_backend_courses_not_supported(h: Harness, monkeypatch):
    """ILIAS-Backend: courses() meldet klar 'noch nicht implementiert' (ohne Netz)."""
    import ilias_core

    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(h.config_dir))
    service = ilias_core.open_service("hhn")
    assert service.backend.name == "ilias"
    with pytest.raises(NotSupportedError, match="für ILIAS noch nicht implementiert"):
        service.backend.courses()
    with pytest.raises(NotSupportedError, match="für ILIAS noch nicht implementiert"):
        service.courses()
    result = h.run("courses", "--instance", "hhn", "--json")
    assert result.exit_code == 1, str(result)
    assert assert_json_error(result, "courses", 1, "not_supported")
    assert "für ILIAS noch nicht implementiert" in result.json()["error"]["message"]
