"""F2 `ilias courses`: Kursliste gegen den lokalen Fake-Moodle (127.0.0.1).

Prüft Menschen- und JSON-Ausgabe, Semesterableitung, Sortierung und die
Exit-Codes aus INTERFACE.md §3. Es wird nie ein echter Server kontaktiert.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from acceptance.leak_check import find_secret_in_text

from ilias_core import open_service
from ilias_core.backends.ilias import IliasBackend
from ilias_core.errors import NotLoggedInError
from ilias_core.timeutil import semester_from_timestamp

from .conftest import INSTANCE, USERNAME, Harness, RunResult

EXPECTED_IDS = [103, 101, 105, 106, 102, 108, 107, 104]  # WiSe zuerst, dann SoSe, None zuletzt


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
    assert data["error"]["message"], str(result)
    return data


# ------------------------------------------------------------------ Semester
@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (0, None),
        (None, None),
        (1773615600, "SoSe 2026"),  # 2026-03-16 (März -> SoSe)
        (1774994400, "SoSe 2026"),  # 2026-04-01
        (1788127200, "SoSe 2026"),  # 2026-08-31 (August -> SoSe)
        (1788213600, "WiSe 2026/27"),  # 2026-09-01 (September -> WiSe)
        (1790805600, "WiSe 2026/27"),  # 2026-10-01
        (1759183200, "WiSe 2025/26"),  # 2025-09-30 (September -> WiSe)
        (1727128800, "WiSe 2024/25"),  # 2024-09-24
        (1801436400, "WiSe 2026/27"),  # 2027-02-01 (Februar -> WiSe Vorjahr)
        (1767999600, "WiSe 2025/26"),  # 2026-01-10 (Januar -> WiSe Vorjahr)
        (1736895600, "WiSe 2024/25"),  # 2025-01-15
    ],
)
def test_semester_derivation_unit(timestamp, expected):
    """F2: reine Funktion der Semesterableitung inkl. der Grenzfälle Mrz/Aug/Sep/Jan."""
    assert semester_from_timestamp(timestamp) == expected


# ------------------------------------------------------------------ Menschen-Ausgabe
def test_courses_human_table(h: Harness):
    """F2: Tabelle mit ID/Kurzname/Name/Semester, neuestes Semester zuerst."""
    assert_logged_in(h)
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    for needle in ("PR1-WS26", "Programmieren 1", "WiSe 2026/27", "SoSe 2026", "Altdatenbank"):
        assert needle in result.stdout, str(result)
    positions = [result.stdout.index(name) for name in ("Mathematik 2", "Programmieren 1", "Altdatenbank")]
    assert positions == sorted(positions), f"Sortierung falsch: {positions}\n{result}"


# ------------------------------------------------------------------ JSON-Ausgabe
def test_courses_json_shape(h: Harness):
    """F2: genau ein JSON-Objekt mit instance/lms/count/courses/timestamp."""
    assert_logged_in(h)
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert result.exit_code == 0, str(result)
    data = result.json()
    assert set(data) == {"instance", "lms", "count", "courses", "timestamp"}, sorted(data)
    assert data["instance"] == INSTANCE and data["lms"] == "moodle"
    assert data["count"] == len(data["courses"]) == 8
    assert datetime.fromisoformat(data["timestamp"]).tzinfo is not None

    by_id = {course["id"]: course for course in data["courses"]}
    assert set(by_id) == {101, 102, 103, 104, 105, 106, 107, 108}
    for course in data["courses"]:
        assert set(course) == {
            "id",
            "fullname",
            "shortname",
            "category",
            "semester",
            "visible",
            "startdate",
            "enddate",
            "url",
        }, sorted(course)

    pr1 = by_id[101]
    assert pr1["fullname"] == "Programmieren 1 (WS 2026/27)"
    assert pr1["shortname"] == "PR1-WS26"
    assert pr1["category"] == 17
    assert pr1["semester"] == "WiSe 2026/27"
    assert pr1["visible"] is True
    assert pr1["startdate"] == "2026-10-01T00:00:00+02:00"
    assert pr1["url"] == f"{h.world.base_url}/course/view.php?id=101"

    alt = by_id[104]
    assert alt["category"] is None
    assert alt["semester"] is None
    assert alt["startdate"] is None
    assert alt["enddate"] is None

    # Bug 5: Semesterregel (Mrz-Aug SoSe, Sep-Dez WiSe, Jan/Feb WiSe Vorjahr)
    assert by_id[106]["semester"] == "SoSe 2026"  # Start 2026-03-16
    assert by_id[107]["semester"] == "WiSe 2024/25"  # Start 2024-09-24
    assert by_id[108]["semester"] == "WiSe 2025/26"  # Start 2026-01-10

    # Bug 3: HTML-Entities werden in der Kernschicht dekodiert (auch im JSON)
    assert by_id[106]["fullname"] == "Dienste --> Support & Hilfe"
    assert by_id[106]["shortname"] == "ENT>1"


def test_courses_sorted_newest_first_null_last(h: Harness):
    assert_logged_in(h)
    data = h.run("courses", "--instance", INSTANCE, "--json").json()
    assert [course["id"] for course in data["courses"]] == EXPECTED_IDS


def test_courses_hidden_course_is_marked_in_json(h: Harness):
    """visible == 0 wird als bool gemeldet."""
    assert_logged_in(h)
    data = h.run("courses", "--instance", INSTANCE, "--json").json()
    hidden = next(c for c in data["courses"] if c["id"] == 105)
    assert hidden["visible"] is False


# ------------------------------------------------------------------ Fehlerfälle
def test_courses_without_token_exit_2(h: Harness):
    """§3: keine gespeicherte Session -> Exit 2, kein Serverkontakt."""
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 2, str(result)
    assert h.world.requests == [], "Server ohne Session kontaktiert"


def test_courses_without_token_json(h: Harness):
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert_error(result, "courses", 2, "not_logged_in")


def test_courses_invalid_token_exit_3(h: Harness):
    """§3: invalidtoken -> Exit 3, kein automatischer Re-Login."""
    assert_logged_in(h)
    h.world.expire_tokens()
    token_calls_before = len(h.world.requests_to("/login/token.php"))
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 3, str(result)
    assert len(h.world.requests_to("/login/token.php")) == token_calls_before, "Re-Login"


def test_courses_server_error_exit_4(h: Harness):
    assert_logged_in(h)
    h.world.rest_mode = "server_error"
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 4, str(result)


def test_courses_html_exit_5(h: Harness):
    """§3: HTML statt JSON -> Exit 5."""
    assert_logged_in(h)
    h.world.rest_mode = "html"
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 5, str(result)


# ------------------------------------------------------------------ Sicherheit
def test_courses_token_never_in_output_or_url(h: Harness):
    """A4: Token nie in stdout/stderr und nie an eine URL angehängt."""
    assert_logged_in(h)
    token = next(iter(h.world.tokens))
    for result in (
        h.run("courses", "--instance", INSTANCE),
        h.run("courses", "--instance", INSTANCE, "--json"),
    ):
        assert result.exit_code == 0, str(result)
        assert token not in result.stdout + result.stderr
        assert not find_secret_in_text(token, result.stdout + result.stderr)
    for request in h.world.requests:
        assert token not in request.path
        assert all(token not in value for values in request.query.values() for value in values)


def test_courses_token_in_post_body_not_query(h: Harness):
    """Moodle-REST: wstoken im POST-Body, niemals im Query-String."""
    assert_logged_in(h)
    h.run("courses", "--instance", INSTANCE)
    rest = h.world.requests_to("/webservice/rest/server.php")
    assert rest, "kein REST-Aufruf"
    assert any(r.form_value("wsfunction") == "core_enrol_get_users_courses" for r in rest)
    for request in rest:
        assert (request.form_value("wstoken") or "").startswith("tok-")
        assert "wstoken" not in request.query


def test_courses_userid_is_sent(h: Harness):
    """F2-Flow: core_enrol_get_users_courses bekommt die userid aus get_site_info."""
    assert_logged_in(h)
    h.run("courses", "--instance", INSTANCE)
    enrol = [
        r
        for r in h.world.requests_to("/webservice/rest/server.php")
        if r.form_value("wsfunction") == "core_enrol_get_users_courses"
    ]
    assert enrol, "core_enrol_get_users_courses wurde nicht aufgerufen"
    assert enrol[-1].form_value("userid") == str(h.world.userid)


def test_courses_username_in_human_output(h: Harness):
    """Die Kursliste ist an den angemeldeten Nutzer gebunden (Fixture)."""
    assert_logged_in(h)
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert result.exit_code == 0
    assert USERNAME == h.world.username


# ------------------------------------------------------------------ ILIAS
def test_ilias_backend_supports_courses_and_ls(tmp_path, monkeypatch):
    """F2/F3 für ILIAS sind per HTML gebaut (HHN S6–S8): kein NotSupported mehr, ohne Session Exit 2."""
    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    backend = open_service("hhn").backend
    assert isinstance(backend, IliasBackend)
    assert backend.supports_courses is True
    with pytest.raises(NotLoggedInError):
        backend.courses()
    with pytest.raises(NotLoggedInError):
        backend.course_contents(101)
