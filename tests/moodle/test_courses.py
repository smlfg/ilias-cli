"""F2 `ilias courses` gegen den lokalen Fake-Moodle."""

from __future__ import annotations

from ilias_core.models import semester_for_startdate

from .conftest import INSTANCE, Harness


def _logged_in(h: Harness):
    result = h.login("--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    return result


# ------------------------------------------------------------------ semester
def test_semester_summer():
    assert semester_for_startdate(_ep(2026, 4, 1)) == "SoSe 2026"
    assert semester_for_startdate(_ep(2026, 9, 30)) == "SoSe 2026"


def test_semester_winter_oct_dec():
    assert semester_for_startdate(_ep(2026, 10, 1)) == "WiSe 2026/27"
    assert semester_for_startdate(_ep(2026, 12, 1)) == "WiSe 2026/27"


def test_semester_winter_jan_mar():
    assert semester_for_startdate(_ep(2027, 2, 1)) == "WiSe 2026/27"
    assert semester_for_startdate(_ep(2027, 1, 15)) == "WiSe 2026/27"


def test_semester_zero_and_missing():
    assert semester_for_startdate(0) is None
    assert semester_for_startdate(None) is None


def _ep(y, m, d):
    from datetime import datetime, timezone

    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


# ------------------------------------------------------------------ courses
def test_courses_human(h: Harness):
    _logged_in(h)
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 0, str(result)
    for expected in ("Mathe 1", "Mathe 2", "Programmieren 1", "Biologie", "Altklausuren"):
        assert expected in result.stdout
    assert "WiSe 2026/27" in result.stdout
    assert "SoSe 2026" in result.stdout
    # Kein Kurs hat semester=null-Text "None"
    assert "None" not in result.stdout


def test_courses_json_shape(h: Harness):
    _logged_in(h)
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert result.exit_code == 0, str(result)
    data = result.json()
    assert data["instance"] == INSTANCE
    assert data["lms"] == "moodle"
    assert data["count"] == 5
    assert len(data["courses"]) == 5
    assert set(data["courses"][0]) == {
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
    by_id = {c["id"]: c for c in data["courses"]}
    assert by_id[1234]["semester"] == "WiSe 2026/27"
    assert by_id[1235]["semester"] == "SoSe 2027"
    assert by_id[1236]["semester"] == "WiSe 2026/27"  # Start Feb 2027
    assert by_id[1237]["semester"] is None
    assert by_id[1237]["startdate"] is None
    assert by_id[1238]["semester"] == "SoSe 2026"
    assert by_id[1234]["category"] == 17
    assert by_id[1234]["visible"] is True
    assert by_id[1234]["url"] == f"{h.world.base_url}/course/view.php?id=1234"
    assert by_id[1234]["startdate"].endswith("+02:00") or by_id[1234]["startdate"].endswith("+01:00")


def test_courses_sorted_newest_first_null_last(h: Harness):
    _logged_in(h)
    data = h.run("courses", "--instance", INSTANCE, "--json").json()
    semesters = [c["semester"] for c in data["courses"]]
    # WiSe 2026/27 (2027-02-01) vor SoSe 2027? SoSe 2027 ist neuer: Apr 2027
    assert semesters[0] == "SoSe 2027"
    assert semesters[-1] is None
    assert semesters == ["SoSe 2027", "WiSe 2026/27", "WiSe 2026/27", "SoSe 2026", None]


def test_courses_without_token_exit_2(h: Harness):
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert result.exit_code == 2, str(result)
    data = result.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "not_logged_in"


def test_courses_invalidtoken_exit_3(h: Harness):
    _logged_in(h)
    h.world.expire_tokens()
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert result.exit_code == 3, str(result)
    assert result.json()["error"]["code"] == "session_expired"


def test_courses_server_error_exit_4(h: Harness):
    _logged_in(h)
    h.world.rest_mode = "server_error"
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 4, str(result)


def test_courses_html_exit_5(h: Harness):
    _logged_in(h)
    h.world.rest_mode = "html"
    result = h.run("courses", "--instance", INSTANCE)
    assert result.exit_code == 5, str(result)


def test_courses_no_token_leak_anywhere(h: Harness):
    _logged_in(h)
    tokens = list(h.world.tokens)
    result = h.run("courses", "--instance", INSTANCE, "--json")
    assert result.exit_code == 0, str(result)
    combined = result.stdout + result.stderr
    for token in tokens:
        assert token not in combined, "Token im Output!"
    for req in h.world.requests:
        for values in req.query.values():
            assert all("tok-" not in v for v in values), f"Token in Query-String: {req.query}"
    # und in keiner URL innerhalb des JSON
    data = result.json()
    for course in data["courses"]:
        assert "tok-" not in course["url"]


def test_courses_get_userid_from_site_info(h: Harness):
    _logged_in(h)
    h.run("courses", "--instance", INSTANCE, "--json")
    calls = [r for r in h.world.requests if r.path == "/webservice/rest/server.php"]
    functions = [r.form_value("wsfunction") for r in calls]
    assert functions[0] == "core_webservice_get_site_info"
    assert "core_enrol_get_users_courses" in functions
    courses_calls = [r for r in calls if r.form_value("wsfunction") == "core_enrol_get_users_courses"]
    assert courses_calls[0].form_value("userid") == str(h.world.userid)
    assert all(r.form_value("wstoken") for r in calls)


def test_courses_ilias_backend_not_supported(h: Harness):
    h.write_config(base_url="https://ilias.example.org", lms="ilias")
    result = h.run("courses")
    assert result.exit_code == 1, str(result)
    assert "nicht implementiert" in result.stderr
    assert "Traceback" not in result.stderr
