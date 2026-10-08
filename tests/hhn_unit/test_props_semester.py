"""Unit-Tests der reinen Semesterfunktionen (Spec §5.3/§13, S6).

Alle Titelformen aus §5.3/§13 müssen erkannt werden, ein Titel ohne Semester
muss ``None`` ergeben (nie raten). Zusätzlich: Der Zeitraum dient nur als Ersatz,
"Anmeldungsende"/"Freie Plätze" nie.
"""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.props import (
    normalize_text,
    semester_from_period,
    semester_from_properties,
    semester_from_title,
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("WiSe 2026/27", "WiSe 2026/27"),
        ("WS 2026/27", "WiSe 2026/27"),
        ("WS26/27", "WiSe 2026/27"),
        ("WiSe26/27", "WiSe 2026/27"),
        ("Wintersemester 2026/27", "WiSe 2026/27"),
        ("_WS26_27", "WiSe 2026/27"),
        ("Kurs_Beispiel_WS26_27", "WiSe 2026/27"),
        ("2026 WS", "WiSe 2026/27"),
        ("Mathematik A für Testzwecke (WiSe 2026/27)", "WiSe 2026/27"),
        ("Archivkurs Beispielwissen WS 2025/26", "WiSe 2025/26"),
        ("SoSe 2026", "SoSe 2026"),
        ("SS 2026", "SoSe 2026"),
        ("SS26", "SoSe 2026"),
        ("SoSe26", "SoSe 2026"),
        ("Sommersemester 2026", "SoSe 2026"),
        ("_SS26", "SoSe 2026"),
        ("2026 SS", "SoSe 2026"),
        ("Orientierungsgruppe 2026 SS", "SoSe 2026"),
        # Kein Semester -> None (Normalfall, kein Fehler, Spec §5.3).
        ("Einführung in Fantasieprotokolle", None),
        ("Lerngruppe Synthese", None),
        ("Anmeldungsende 31. Mär 2027", None),
        ("", None),
    ],
)
def test_semester_from_title(title, expected):
    assert semester_from_title(title) == expected


def test_semester_from_title_ignores_lowercase_words():
    """Kleingeschriebene Wörter ("Klasse", "Fantasie") dürfen kein Semester ergeben."""

    assert semester_from_title("Die große Klasse der Beispiele") is None
    assert semester_from_title("Fantastische Übungen 2026") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("16. Mär 2026 - 31. Aug 2026", "SoSe 2026"),
        ("01. Mrz 2026 - 31. Aug 2026", "SoSe 2026"),
        ("01. Sep 2026 - 28. Feb 2027", "WiSe 2026/27"),
        ("10. Jan 2026 - 31. Mär 2026", "WiSe 2025/26"),
        ("Kein Datum lesbar", None),
        ("", None),
    ],
)
def test_semester_from_period(text, expected):
    assert semester_from_period(text) == expected


def test_semester_from_properties_only_uses_period():
    """Nur "Zeitraum"/"Kurszeitraum"/"Period" zählt, nie "Anmeldungsende"/"Freie Plätze"."""

    assert semester_from_properties(
        {
            "Anmeldungsende": "31. Mär 2027, 12:00",
            "Freie Plätze": "0",
            "Zeitraum": "16. Mär 2026 - 31. Aug 2026",
        }
    ) == "SoSe 2026"
    assert semester_from_properties({"Anmeldungsende": "16. Mär 2026"}) is None


def test_normalize_text_decodes_entities_and_nfc():
    """Entities dekodieren, Leerraum normalisieren, nie kürzen (Spec §6.3/§13.9)."""

    import unicodedata

    nfd = unicodedata.normalize("NFD", "Lösung")
    assert normalize_text(f"  {nfd}   &amp;   Übersicht  ") == "Lösung & Übersicht"
    assert normalize_text(unicodedata.normalize("NFD", "Lösung")) == "Lösung"
