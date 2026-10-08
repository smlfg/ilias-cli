"""Unit-Tests für Größe, Datum und Semester aus ``ilias_core.ilias_html.props``."""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.props import (
    decode_text,
    parse_date,
    parse_file_props,
    parse_size,
    parse_suffix,
    semester_from_title,
    semester_from_zeitraum,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("203.45 KB", round(203.45 * 1024)),
        ("1.5 MB", round(1.5 * 1024**2)),
        ("1,5 MB", round(1.5 * 1024**2)),
        ("2,25 MB", round(2.25 * 1024**2)),
        ("820 KB", 820 * 1024),
        ("1 GB", 1024**3),
        ("1.00 GB", 1024**3),
        ("512 Bytes", 512),
        ("pdf", None),
        ("", None),
        ("25. Sep 2026, 10:12", None),
        (None, None),
    ],
)
def test_parse_size(text, expected):
    assert parse_size(text) == expected


def test_parse_date_absolute():
    assert parse_date("25. Sep 2026, 10:12").startswith("2026-09-25T10:12")


def test_parse_date_relative_is_none_or_iso():
    value = parse_date("Heute, 09:15")
    assert value is None or value.endswith("09:15:00+02:00") or "T09:15" in value


def test_parse_file_props_tolerates_extra_properties():
    suffix, size, size_text, modified = parse_file_props(
        ["pdf", "1.5 MB", "Version: 2", "25. Sep 2026, 10:12"]
    )
    assert suffix == "pdf"
    assert size == round(1.5 * 1024**2)
    assert size_text == "1.5 MB"
    assert modified.startswith("2026-09-25T10:12")


def test_parse_suffix():
    assert parse_suffix(["pdf", "1.5 MB"]) == "pdf"
    assert parse_suffix(["1.5 MB"]) is None


@pytest.mark.parametrize(
    "title,semester",
    [
        ("Mathematik A (WiSe 2026/27)", "WiSe 2026/27"),
        ("Archiv WS 2025/26", "WiSe 2025/26"),
        ("Traumwirtschaft_Beispiel_WS26_27", "WiSe 2026/27"),
        ("TSTB9.1 Synthesekunde (990041) 2026 WS", "WiSe 2026/27"),
        ("Beispiel WiSe26/27", "WiSe 2026/27"),
        ("Orientierung 2026 WS", "WiSe 2026/27"),
        ("Einführung ohne Semester", None),
        ("Kurs SoSe26", "SoSe 2026"),
        ("Kurs _SS26", "SoSe 2026"),
        ("Kurs SS 2026", "SoSe 2026"),
        ("Kurs 2026 SS", "SoSe 2026"),
    ],
)
def test_semester_from_title(title, semester):
    assert semester_from_title(title) == semester


def test_semester_from_zeitraum():
    assert semester_from_zeitraum("16. Mär 2026 - 31. Aug 2026") == "SoSe 2026"
    assert semester_from_zeitraum("1. Okt 2025 - 28. Feb 2026") == "WiSe 2025/26"
    assert semester_from_zeitraum("Anmeldungsende") is None


def test_decode_text_entities_and_nfc():
    assert decode_text("Übung 3 --&gt; Lösung") == "Übung 3 --> Lösung"
    nfd = "Lo\u0308sung"
    assert decode_text(nfd) == "Lösung"
