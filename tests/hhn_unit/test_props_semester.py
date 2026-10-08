"""Unit-Tests für ilias_credits props.semester_from_title (Spec §5.3/§13, L9).

Synthetische Titelformen, kein Netz, kein Fake. Lauf: `uv run pytest tests/hhn_unit -q`.
"""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.props import (
    parse_german_date,
    semester_from_period,
    semester_from_title,
)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Mathematik A für Testzwecke (WiSe 2026/27)", "WiSe 2026/27"),
        ("Archivkurs Beispielwissen WS 2025/26", "WiSe 2025/26"),
        ("Kurs mit WS26/27", "WiSe 2026/27"),
        ("Beispielökonomie Grundkurs WiSe26/27", "WiSe 2026/27"),
        ("Wintersemester 2026/27 Mathematik", "WiSe 2026/27"),
        ("Traumwirtschaft_Beispiel_WS26_27", "WiSe 2026/27"),
        ("TSTB9.1 Synthesekunde (990041) 2026 WS", "WiSe 2026/27"),
        ("Orientierungsgruppe 2026 WS", "WiSe 2026/27"),
        ("Ein Wintersemester", None),
        ("Sommersemester 2026", "SoSe 2026"),
        ("Mathematik SoSe 2026", "SoSe 2026"),
        ("Mathematik SS 2026", "SoSe 2026"),
        ("Mathematik SS26", "SoSe 2026"),
        ("Mathematik SoSe26", "SoSe 2026"),
        ("Fach_SS26", "SoSe 2026"),
        ("Fach 2026 SS", "SoSe 2026"),
        ("Einführung in Fantasieprotokolle", None),
        ("Mathematik B für Testzwecke", None),
        ("Lerngruppe Synthese", None),
        ("", None),
        (None, None),
        ("Kurs ohne Angabe von 2026", None),
        ("Anmeldungsende 31. Mär 2027, 12:00", None),
    ],
)
def test_semester_from_title(title, expected):
    assert semester_from_title(title) == expected


def test_semester_from_period():
    assert semester_from_period("16. Mär 2026 - 31. Aug 2026") == "SoSe 2026"
    assert semester_from_period("1. Sep 2026 - 31. Jan 2027") == "WiSe 2026/27"
    assert semester_from_period("10. Jan 2026 - 15. Feb 2026") == "WiSe 2025/26"
    assert semester_from_period(None) is None
    assert semester_from_period("keine Angabe") is None


def test_parse_german_date():
    assert parse_german_date("16. Mär 2026") == (2026, 3, 16)
    assert parse_german_date("3. Okt 2026, 09:00") == (2026, 10, 3)
    assert parse_german_date("30. Dez 2025") == (2025, 12, 30)
    assert parse_german_date("kein Datum") is None
