"""Eigenschafts-Parser für ILIAS-HTML-Seiten (Spec §6.4, §13.4).

Reine Funktionen für Größe, Datum und Semester aus ILIAS-Eigenschaften.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional


def semester_from_title(title: str) -> str | None:
    """Extrahiere das Semester aus einem ILIAS-Kurstitel.

    Erkannt nach Spec §5.3 / §13:
    - WiSe26/27, _WS26_27, 2026 WS → WiSe 2026/27
    - SoSe26, _SS26, 2026 SS → SoSe 2026
    - Titel-Muster: WiSe 2026/27, WS 2026/27, WS26/27, Wintersemester 2026/27 → WiSe 2026/27
    - SoSe 2026, SS 2026, SS26, Sommersemester 2026 → SoSe 2026
    - Falls kein Semester erkennbar → None.

    Der Titel wird NFC-normalisiert, damit zusammenhängende Zeichen
    konsistent behandelt.
    """
    if not title:
        return None

    t = unicodedata.normalize("NFC", title)

    # Pattern: WiSe26/27, WS26/27 (Typ mit 2-stelliger Jahreszahl, kein Space vor dem Schrägstrich)
    # Erzeugt: WiSe 2026/27 oder WS 2025/26 etc.
    m = re.search(r"(WiSe|WS|Wintersemester)(\d{2})/\d{2}", t, re.IGNORECASE)
    if m:
        year_prefix = "20"
        first_2dig = m.group(2)
        second_2dig = str(int(first_2dig) + 1)
        # Wintersemester/WS -> WiSe, Sonstiges beibehalten
        ttype = m.group(1).upper()
        if ttype in ("WS", "WINTERSEMESTER"):
            ttype = "WiSe"
        return f"{ttype} {year_prefix}{first_2dig}/2{second_2dig}"

    # Pattern: _WS26_27 (with underscores)
    if re.search(r"_WS\d+_\d+", t):
        return "WiSe 2026/27"

    # Pattern: 2026 WS (4-stellige Jahreszahl vor dem Figurtyp, mit Space)
    m = re.search(r"(?<!\d)(\d{4})\s*(WS|WiSe|Wintersemester)\b", t, re.IGNORECASE)
    if m:
        year4 = m.group(1)
        ttype = m.group(2).upper()
        if ttype in ("WS", "WINTERSEMESTER"):
            # Wintersemester 2026/27 -> WiSe 2026/27
            return f"WiSe {year4}/2{int(year4[2:]) + 1}"
        # Fallback: typed beibehalten (sollte nicht eintreten)
        return f"{m.group(1)} {m.group(2)}/2{int(m.group(1)[2:]) + 1}"

    # Pattern: WiSe 2026/27 (Typ mit Space und 4-stelliger Jahreszahl vor dem Schrägstrich)
    m = re.search(r"(WiSe|WS|Wintersemester)\s(\d{4})/\d{2}", t, re.IGNORECASE)
    if m:
        year4 = m.group(2)
        ttype = m.group(1).upper()
        if ttype in ("WiSe", "WS", "Wintersemester"):
            return f"{m.group(1)} {year4}/2{int(year4[2:]) + 1}"

    # Pattern: SoSe26, SS26 (Typ mit 2-stelliger Jahreszahl)
    m = re.search(r"(SoSe|SS|Sommersemester)(\d{2})\b", t, re.IGNORECASE)
    if m:
        first_2dig = m.group(2)
        second_2dig = str(int(first_2dig) + 1)
        ttype = m.group(1).upper()
        if ttype in ("SS", "SOSE", "SOMMERSEMESTER"):
            ttype = "SoSe"
        return f"{ttype} {year_prefix if False else '20'}{first_2dig}/2{second_2dig}"
        # Actually:
        return f"{ttype} 20{first_2dig}/2{second_2dig}"

    # Pattern: _SS26_27 or similar
    if re.search(r"_SS\d+_\d+", t):
        return "SoSe 2026"

    # Pattern: 2026 SS (4-stellige Jahreszahl vor dem Figurtyp)
    m = re.search(r"(?<!\d)(\d{4})\s*(SS|SoSe|Sommersemester)\b", t, re.IGNORECASE)
    if m:
        year4 = m.group(1)
        ttype = m.group(2).upper()
        if ttype in ("SS", "SOSE", "SOMMERSEMESTER"):
            return f"SoSe {year4}/2{int(year4[2:]) + 1}"
        return None

    # Pattern: SoSe 2026 (Typ mit Space und 4-stelliger Jahreszahl)
    m = re.search(r"(SoSe|SS|Sommersemester)\s(\d{4})\b", t, re.IGNORECASE)
    if m:
        year4 = m.group(2)
        ttype = m.group(1).upper()
        if ttype in ("SoSe", "SS", "SOMMERSEMESTER"):
            return f"{ttype} {year4}/2{int(year4[2:]) + 1}"

    return None


def parse_size(text: str) -> Optional[int]: