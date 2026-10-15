"""Menschen-Ausgabe für ILIAS (Spec §5.1/§6.5): Kurstabelle, ls-Kopfzeile, Größen in "B".

Nur synthetische Daten, kein Netzwerk.
"""

from __future__ import annotations

import pytest

from ilias_cli import output
from ilias_core.ilias_html.props import parse_size
from ilias_core.models import Course, CourseContentsResult, CoursesResult

LONG_TITLE = "Synthetische Einführung in ausgedachte Grundlagen der Informatik mit sehr langem Titel " * 2


def _ilias_courses() -> CoursesResult:
    return CoursesResult(
        instance="hhn",
        lms="ilias",
        courses=[
            Course(id=900101, fullname=LONG_TITLE.strip(), shortname="", semester="WiSe 2026/27", type="crs"),
            Course(id=900150, fullname="Lerngruppe Synthese", shortname="", semester=None, type="grp"),
        ],
    )


def _set_width(monkeypatch, columns: int) -> None:
    import os

    monkeypatch.setattr(output.shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((columns, 24)))


def test_ilias_courses_table_layout(monkeypatch, capsys):
    _set_width(monkeypatch, 240)
    output.print_courses(_ilias_courses())
    out = capsys.readouterr().out
    header = next(line for line in out.splitlines() if "ID (ref_id)" in line)
    for col in ("ID (ref_id)", "Typ", "Titel", "Semester"):
        assert col in header, header
    assert "Kurzname" not in out
    assert "900101" in out and "crs" in out and "grp" in out


def test_ilias_courses_table_uses_terminal_width(monkeypatch, capsys):
    _set_width(monkeypatch, 240)
    output.print_courses(_ilias_courses())
    out = capsys.readouterr().out
    assert any(LONG_TITLE.strip() in line for line in out.splitlines()), out  # nicht bei 80 umgebrochen
    assert max(len(line) for line in out.splitlines()) > 80


def test_ilias_courses_table_narrow_terminal_folds(monkeypatch, capsys):
    _set_width(monkeypatch, 60)
    output.print_courses(_ilias_courses())
    out = capsys.readouterr().out
    assert max(len(line) for line in out.splitlines()) <= 60, out


def test_moodle_courses_table_unchanged(capsys):
    result = CoursesResult(
        instance="hs-mannheim",
        lms="moodle",
        courses=[Course(id=7, fullname="Ausgedachter Kurs", shortname="AK1", semester="WS 2026/27")],
    )
    output.print_courses(result)
    out = capsys.readouterr().out
    header = next(line for line in out.splitlines() if "Kurzname" in line)
    for col in ("ID", "Kurzname", "Name", "Semester"):
        assert col in header, header
    assert "ID (ref_id)" not in out


@pytest.mark.parametrize("shortname", ["", None, "   "])
def test_ls_header_without_empty_parentheses(capsys, shortname):
    course = {"id": 900101, "fullname": "990041 Grundlagen Synthese", "shortname": shortname}
    result = CourseContentsResult(instance="hhn", lms="ilias", course=course, sections=[])
    output.print_contents(result)
    first = capsys.readouterr().out.splitlines()[0]
    assert first.strip() == "990041 Grundlagen Synthese", first
    assert "()" not in first
    assert result.to_json_dict()["course"] == course  # JSON unverändert


def test_ls_header_keeps_shortname_when_present(capsys):
    course = {"id": 7, "fullname": "Ausgedachter Kurs", "shortname": "AK1"}
    output.print_contents(CourseContentsResult(instance="hs-mannheim", lms="moodle", course=course))
    assert capsys.readouterr().out.splitlines()[0].strip() == "Ausgedachter Kurs (AK1)"


@pytest.mark.parametrize(
    "text,expected",
    [("512 B", 512), ("1 B", 1), ("512 Bytes", 512), ("1 Byte", 1), ("0,5 KB", 512), ("12 Bilder", None)],
)
def test_parse_size_bytes_unit(text, expected):
    assert parse_size(text) == expected
