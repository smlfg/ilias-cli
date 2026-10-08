"""F2 `ilias courses` gegen den lokalen Fake-Moodle (127.0.0.1).

Deckt die Anforderungen aus ANFORDERUNGEN.md §3 (F2) und INTERFACE.md §3 ab:
JSON-Form, Semester-Ableitung, HTTP-Flow (userid aus der Site-Info) und die
Exit-Codes 2/3/4/5. Der Token darf nirgends auftauchen (A4).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from acceptance.leak_check import find_secret_in_text

from ilias_core.timeutil import semester_from_timestamp

from .conftest import INSTANCE, Harness, RunResult
from .fixtures import COURSE_IDS, TS

COURSES_KEYS = {
    "id",
    "fullname",
    "shortname",
    "category",
    "semester",
    "visible",
    "startdate",
    "enddate",
    "url",
}
ILIAS_INSTANCE = "hhn-test"


def login_and(h: Harness) -> None:
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)


def courses(h: Harness, *extra: str) -> RunResult:
    return h.run("courses", "--instance", INSTANCE, *extra)


def by_id(data: dict) -> dict[int, dict]:
    return {course["id"]: course for course in data["courses"]}


def assert_berlin_iso(value: str) -> None:
    stamp = datetime.fromisoformat(value)
    assert stamp.tzinfo is not None, value
    assert str(stamp.utcoffset()) in {"2:00:00", "1:00:00"}, value


# ------------------------------------------------------------------ Semester (rein)
@pytest.mark.parametrize(
    "startdate, expected",
    [
        (TS["2026-04-15"], "SoSe 2026"),  # April -> Sommersemester
        (1774994400, "SoSe 2026"),  # 2026-04-01, erster Tag des SoSe
        (TS["2026-09-30"], "SoSe 2026"),  # letzter Septemberstag bleibt SoSe
        (TS["2026-10-01"], "WiSe 2026/27"),  # Oktober -> WiSe mit Folgejahr
        (TS["2026-12-31"], "WiSe 2026/27"),
        (1798758000, "WiSe 2026/27"),  # 2027-01-01 -> WiSe des Vorjahres
        (1801436400, "WiSe 2026/27"),  # 2027-02-01, der geforderte Fall
        (TS["2026-07-31"], "SoSe 2026"),
        (TS["2025-10-01"], "WiSe 2025/26"),
        (TS["2026-04-17"], "SoSe 2026"),
        (0, None),  # "kein Datum gesetzt"
        (None, None),
    ],
)
def test_semester_from_startdate(startdate, expected):
    """F2/N5: Semester wird aus dem Startdatum in Europe/Berlin abgeleitet."""
    assert semester_from_timestamp(startdate) == expected


def test_semester_march_is_previous_winter_semester():
    """Januar bis März gehören zum im Vorjahr begonnenen Wintersemester."""
    assert semester_from_timestamp(1806444000) == "WiSe 2026/27"  # 2027-03-31


# ------------------------------------------------------------------ Kommando
def test_courses_help(h: Harness):
    """`ilias courses --help` und `ilias ls --help` funktionieren (F2/F3)."""
    for command in (h.run("--help"), h.run("courses", "--help"), h.run("ls", "--help")):
        assert command.exit_code == 0, str(command)
    assert "courses" in h.run("--help").stdout
    assert "ls" in h.run("--help").stdout
    for flag in ("--json", "--instance"):
        assert flag in h.run("courses", "--help").stdout, flag
    for flag in ("--json", "--instance", "--depth"):
        assert flag in h.run("ls", "--help").stdout, flag


def test_courses_human_table(h: Harness):
    """F2: Tabelle mit ID, Kurzname, Name und Semester - neuestes Semester zuerst."""
    login_and(h)
    result = courses(h)
    assert result.exit_code == 0, str(result)
    out = result.stdout
    assert "Eigene Kurse" in out
    for header in ("ID", "Kurzname", "Name", "Semester"):
        assert header in out, f"Spalte {header} fehlt: {out}"
    # Umlaute und Semesternamen stehen drin
    assert "Programmieren 1 (WS 2026/27)" in out
    assert "WiSe 2026/27" in out and "SoSe 2026" in out
    assert "Seminar: Abschlussarbeiten" in out
    assert "unbekannt" in out  # Kurs ohne Startdatum
    # neuestes Semester zuerst, unbekanntes Semester ganz unten
    assert out.index("SoSe 2026") < out.index("WiSe 2025/26") < out.index("unbekannt"), out


def test_courses_json_shape(h: Harness):
    """F2/§3: genau ein JSON-Objekt mit instance, lms, count, courses, timestamp."""
    login_and(h)
    result = courses(h, "--json")
    assert result.exit_code == 0, str(result)
    assert result.stdout.strip().startswith("{"), "stdout muss mit dem JSON-Objekt beginnen"
    data = result.json()
    assert set(data) == {"instance", "lms", "count", "courses", "timestamp"}, sorted(data)
    assert data["instance"] == INSTANCE
    assert data["lms"] == "moodle"
    assert data["count"] == len(data["courses"]) == 5
    assert_berlin_iso(data["timestamp"])
    for course in data["courses"]:
        assert set(course) == COURSES_KEYS, sorted(course)


def test_courses_json_values(h: Harness):
    """F2: Felder je Kurs inkl. Semester, ISO-Daten, Kategorie und URL."""
    login_and(h)
    data = courses(h, "--json").json()
    courses_by_id = by_id(data)

    winter = courses_by_id[COURSE_IDS["PR1-WS26"]]
    assert winter["shortname"] == "PR1-WS26"
    assert winter["fullname"] == "Programmieren 1 (WS 2026/27)"
    assert winter["semester"] == "WiSe 2026/27"
    assert winter["category"] == 17
    assert winter["visible"] is True
    assert winter["startdate"] == "2026-10-01T00:00:00+02:00"  # N5
    assert winter["enddate"] == "2027-03-30T00:00:00+02:00"
    assert winter["url"] == f"{h.world.base_url}/course/view.php?id=51234"
    for value in (winter["startdate"], winter["enddate"], data["timestamp"]):
        assert_berlin_iso(value)

    summer = courses_by_id[COURSE_IDS["MATH1-SS26"]]
    assert summer["semester"] == "SoSe 2026"
    assert summer["startdate"] == "2026-04-15T00:00:00+02:00"

    archived = courses_by_id[COURSE_IDS["EINS-SEM25"]]
    assert archived["visible"] is False, "visible: 0 im JSON"
    assert archived["semester"] == "WiSe 2025/26"

    without_date = courses_by_id[COURSE_IDS["SEM-ARBEIT"]]
    assert without_date["semester"] is None, "startdate 0 -> Semester unbekannt"
    assert without_date["startdate"] is None and without_date["enddate"] is None
    assert without_date["category"] is None, "fehlende Kategorie -> null"


def test_courses_sorted_newest_first(h: Harness):
    """F2: Sortierung nach Semester (neuestes zuerst, unbekanntes zuletzt)."""
    login_and(h)
    data = courses(h, "--json").json()
    semesters = [course["semester"] for course in data["courses"]]
    years = [0 if s is None else int(s.split()[1][:4]) for s in semesters]
    assert years == sorted(years, reverse=True), semesters
    assert semesters[-1] is None, "Kurs ohne Semester muss hinten stehen"
    # gleiches Jahr: dann der Titel alphabetisch
    assert [c["shortname"] for c in data["courses"][:2]] == ["MATH1-SS26", "MATH1-SS26-VL"]


def test_courses_flow_uses_stored_token_and_userid(h: Harness):
    """Ablauf: gespeicherter Token -> Site-Info (userid) -> core_enrol_get_users_courses."""
    login_and(h)
    before = len(h.world.requests_to("/webservice/rest/server.php"))
    assert courses(h).exit_code == 0

    calls = h.world.requests_to("/webservice/rest/server.php")[before:]
    assert [call.wsfunction for call in calls] == [
        "core_webservice_get_site_info",
        "core_enrol_get_users_courses",
    ], [call.wsfunction for call in calls]
    assert calls[1].form_value("userid") == str(h.world.userid)
    assert calls[1].form_value("moodlewsrestformat") == "json"
    # N2: eigener User-Agent
    assert all(call.headers.get("User-Agent", "").startswith("ilias-cli/") for call in calls)


def test_courses_token_in_body_never_in_url(h: Harness):
    """A4: der Token steht im POST-Body und niemals in Pfad oder Query."""
    login_and(h)
    assert courses(h, "--json").exit_code == 0
    tokens = list(h.world.tokens)
    assert tokens
    rest_calls = h.world.requests_to("/webservice/rest/server.php")
    assert rest_calls
    for call in rest_calls:
        assert call.method == "POST"
        assert call.form_value("wstoken") in tokens
        assert call.query == {}, f"REST-Aufruf mit Parametern in der URL: {call.query}"
        for token in tokens:
            assert call.query_value("wstoken") is None, "wstoken in der Query"
            assert token not in call.path, "Token im Pfad"


def test_courses_token_never_in_output(h: Harness):
    """A4: der Token erscheint in keiner Ausgabe von courses."""
    login_and(h)
    results = [courses(h), courses(h, "--json")]
    tokens = list(h.world.tokens)
    assert tokens
    for result in results:
        assert result.exit_code == 0, str(result)
        for token in tokens:
            assert not find_secret_in_text(token, result.stdout + result.stderr), "Token in der Ausgabe"
            assert "wstoken" not in result.stdout, "Token-Parameter in der Ausgabe"


# ------------------------------------------------------------------ Fehler
def test_courses_without_token_exit_2(h: Harness):
    """§3: ohne gespeicherte Session -> Exit 2."""
    result = courses(h)
    assert result.exit_code == 2, str(result)
    assert "login" in result.stderr


def test_courses_without_token_json(h: Harness):
    result = courses(h, "--json")
    assert result.exit_code == 2, str(result)
    data = result.json()
    assert data["error"]["code"] == "not_logged_in"
    assert data["exit_code"] == 2
    assert not h.world.requests_to("/webservice/rest/server.php"), "ohne Token darf nicht abgefragt werden"


@pytest.mark.parametrize("mode", ["invalid_token"])
def test_courses_invalid_token_exit_3(h: Harness, mode: str):
    """§3/A5: Server meldet invalidtoken -> Exit 3, kein automatischer Re-Login."""
    login_and(h)
    h.world.rest_mode = mode
    logins_before = len(h.world.requests_to("/login/token.php"))
    result = courses(h, "--json")
    assert result.exit_code == 3, str(result)
    assert result.json()["error"]["code"] == "session_expired"
    assert len(h.world.requests_to("/login/token.php")) == logins_before, "kein Re-Login"


def test_courses_invalid_token_from_courses_endpoint_exit_3(h: Harness):
    """Auch der Kurs-Endpunkt selbst kann invalidtoken melden."""
    login_and(h)
    h.world.courses_mode = "invalid_token"
    result = courses(h)
    assert result.exit_code == 3, str(result)


def test_courses_expired_token_exit_3(h: Harness):
    """Abgelaufener Token (serverseitig entfernt) -> Exit 3."""
    login_and(h)
    h.world.expire_tokens()
    assert courses(h).exit_code == 3


@pytest.mark.parametrize(
    "attribute, mode",
    [("courses_mode", "server_error"), ("rest_mode", "server_error")],
)
def test_courses_server_error_exit_4(h: Harness, attribute: str, mode: str):
    """§3: HTTP 5xx -> Exit 4 (Netzwerk/Server)."""
    login_and(h)
    setattr(h.world, attribute, mode)
    result = courses(h, "--json")
    assert result.exit_code == 4, str(result)
    assert result.json()["error"]["code"] == "network_error"


def test_courses_network_error_exit_4(h: Harness):
    """§3: Server nicht erreichbar -> Exit 4."""
    login_and(h)
    h.world.stop()
    assert courses(h).exit_code == 4


def test_courses_html_response_exit_5(h: Harness):
    """§3: HTML (Wartungsseite) statt JSON -> Exit 5."""
    login_and(h)
    h.world.courses_mode = "html"
    result = courses(h, "--json")
    assert result.exit_code == 5, str(result)
    assert result.json()["error"]["code"] == "parse_error"


@pytest.mark.parametrize("mode", ["broken", "object"])
def test_courses_unexpected_response_exit_5(h: Harness, mode: str):
    """§3: unerwartete Antwort (Pflichtfelder fehlen, Objekt statt Liste) -> Exit 5."""
    login_and(h)
    h.world.courses_mode = mode
    result = courses(h)
    assert result.exit_code == 5, str(result)
    assert "Traceback" not in result.stderr, str(result)


def test_courses_access_denied_exit_1(h: Harness):
    """Webservice verweigert die Funktion -> klarer Fehler mit Exit 1."""
    login_and(h)
    h.world.courses_mode = "access_denied"
    result = courses(h, "--json")
    assert result.exit_code == 1, str(result)
    assert result.json()["error"]["code"] == "auth_failed"


def test_courses_ilias_backend_not_supported(h: Harness):
    """ILIAS hat courses/ls (noch) nicht - klarer Hinweis statt Absturz."""
    h.write_config(instance=ILIAS_INSTANCE, lms="ilias")
    for args, exit_code in (
        (("courses", "--instance", ILIAS_INSTANCE), 1),
        (("ls", "51234", "--instance", ILIAS_INSTANCE), 1),
    ):
        result = h.run(*args, "--json")
        assert result.exit_code == exit_code, str(result)
        data = result.json()
        assert data["error"]["code"] == "not_supported", str(result)
        assert "noch nicht implementiert" in data["error"]["message"], str(result)
        assert data["lms"] == "ilias"
        assert not h.world.requests, "der ILIAS-Pfad darf nichts abfragen"
