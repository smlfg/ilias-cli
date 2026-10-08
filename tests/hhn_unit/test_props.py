"""Unit-Tests für ilias_core.ilias_html.props (Spec §6.4, §13.4)."""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.props import parse_size, parse_date, extract_suffix, extract_file_props


class TestParseSize:
    """§6.4/§13.4: parse_size akzeptiert Punkt UND Komma als Dezimaltrenner, Basis 1024."""

    @pytest.mark.parametrize("text,expected", [
        ("196.37 KB", round(196.37 * 1024)),
        ("6.8 KB", round(6.8 * 1024)),
        ("1.5 MB", round(1.5 * 1024**2)),
        ("1,5 MB", round(1.5 * 1024**2)),
        ("2,25 MB", round(2.25 * 1024**2)),
        ("820 KB", 820 * 1024),
        ("1 GB", 1024**3),
        ("1.00 GB", 1024**3),
        ("512 Bytes", 512),
        ("512 Byte", 512),
        ("203.45 KB", round(203.45 * 1024)),
    ])
    def test_parse_size_valid(self, text: str, expected: int):
        got = parse_size(text)
        assert isinstance(got, int)
        # ±1 Byte Toleranz durch Rundung
        assert abs(got - expected) <= 1, f"{text}: got {got}, expected {expected}"

    @pytest.mark.parametrize("text", [
        "pdf",
        "",
        "keine Größe",
        "100",
        "100 TB",
    ])
    def test_parse_size_invalid(self, text: str):
        assert parse_size(text) is None


class TestParseDate:
    """§6.4/§13.4: Datum in ISO 8601 (Europe/Berlin)."""

    def test_parse_absolute_date(self):
        """Absolutes Datum: '25. Sep 2026, 10:12'."""
        result = parse_date("25. Sep 2026, 10:12")
        assert result is not None
        assert result.startswith("2026-09-25T10:12")

    def test_parse_absolute_date_no_leading_zero(self):
        """Tag ohne führende Null: '3. Okt 2026, 08:00'."""
        result = parse_date("3. Okt 2026, 08:00")
        assert result is not None
        assert result.startswith("2026-10-03T08:00")

    def test_parse_relative_heute(self):
        """Relativ: 'Heute, 09:15'."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ref = datetime(2026, 10, 8, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        result = parse_date("Heute, 09:15", reference_date=ref)
        assert result is not None
        assert result.startswith("2026-10-08T09:15")

    def test_parse_relative_gestern(self):
        """Relativ: 'Gestern, 14:30'."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ref = datetime(2026, 10, 8, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        result = parse_date("Gestern, 14:30", reference_date=ref)
        assert result is not None
        assert result.startswith("2026-10-07T14:30")

    def test_parse_relative_morgen(self):
        """Relativ: 'Morgen, 08:00'."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ref = datetime(2026, 10, 8, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        result = parse_date("Morgen, 08:00", reference_date=ref)
        assert result is not None
        assert result.startswith("2026-10-09T08:00")

    @pytest.mark.parametrize("text", [
        "pdf",
        "",
        "kein Datum",
        "2026-09-25",
    ])
    def test_parse_date_invalid(self, text: str):
        assert parse_date(text) is None


class TestExtractSuffix:
    """Endung aus Eigenschaften extrahieren."""

    def test_extract_suffix_first_prop(self):
        props = ["pdf", "1.5 MB", "25. Sep 2026, 10:12"]
        assert extract_suffix(props) == "pdf"

    def test_extract_suffix_lowercase(self):
        props = ["PDF", "1.5 MB"]
        assert extract_suffix(props) == "pdf"

    def test_extract_suffix_empty(self):
        assert extract_suffix([]) is None
        assert extract_suffix([""]) is None


class TestExtractFileProps:
    """Alle Datei-Eigenschaften extrahieren."""

    def test_extract_all(self):
        props = ["pdf", "1.5 MB", "Version: 2", "25. Sep 2026, 10:12"]
        result = extract_file_props(props)
        assert result["suffix"] == "pdf"
        assert result["size"] == round(1.5 * 1024**2)
        assert result["size_text"] == "1.5 MB"
        assert result["timemodified"] is not None
        assert result["timemodified"].startswith("2026-09-25T10:12")

    def test_extract_comma_size(self):
        props = ["pdf", "2,25 MB", "Heute, 09:15"]
        result = extract_file_props(props)
        assert result["suffix"] == "pdf"
        assert result["size"] == round(2.25 * 1024**2)
        assert result["size_text"] == "2,25 MB"

    def test_extract_no_size(self):
        props = ["pdf", "Version: 2"]
        result = extract_file_props(props)
        assert result["suffix"] == "pdf"
        assert result["size"] is None
        assert result["size_text"] is None

    def test_extract_no_date(self):
        props = ["pdf", "1.5 MB"]
        result = extract_file_props(props)
        assert result["timemodified"] is None