"""Fixture-Daten für `ilias ls` (S7/S8): Kurs-, Ordner- und Gruppeninhalte der Fake-HHN.

Alles ausgedacht (ref_ids >= 900101); nur die Struktur folgt den Live-Befunden
(docs/HHN_2FA_SPEC.md §13.3-§13.9). Gerendert von tests/hhn/fake_hhn.py.
"""

from __future__ import annotations

import unicodedata

LONG_TITLE = "Zusammenfassung aller Kapitel mit ausführlichen Beispielen und Lösungswegen Teil 1"
# NFD (zerlegte Umlaute) im HTML; erwartet wird NFC in der Ausgabe (Spec §6.3)
NFD_TITLE = unicodedata.normalize("NFD", "Lösungshinweise Übersicht")
NFC_TITLE = unicodedata.normalize("NFC", NFD_TITLE)

# Container: ref_id -> Blöcke. Block = (Titel, itgr_ref oder None, Items).
# Objektblöcke (itgr) stehen wie an der HHN VOR dem Restblock "Inhalt".
# Item: type, ref_id, title, props(list[str]), offline, inline (Datei mit eigenem Icon), target (crsr)
CONTAINERS: dict[int, list[tuple[str, int | None, list[dict]]]] = {
    900101: [
        ("Klausurvorbereitung", 900181, [
            {"type": "fold", "ref_id": 900203, "title": "[Klausur] Altklausuren"},
        ]),
        ("Inhalt", None, [
            {"type": "fold", "ref_id": 900201, "title": "Übungsblätter"},
            {"type": "file", "ref_id": 900301, "title": "Skript Kapitel 1", "inline": True,
             "props": ["pdf", "1.5 MB", "Version: 2", "25. Sep 2026, 10:12"]},
            {"type": "file", "ref_id": 900302, "title": LONG_TITLE,
             "props": ["pdf", "820 KB", "1. Okt 2026, 08:00"]},
            {"type": "webr", "ref_id": 900401, "title": "Übung 3 --> Lösung (Link)"},
            {"type": "exc", "ref_id": 900501, "title": "Hausaufgabe 1", "props": ["Abgabefrist: 5 Tage, 12 Stunden"]},
            {"type": "tst", "ref_id": 900601, "title": "Selbsttest Kapitel 1"},
            {"type": "frm", "ref_id": 900701, "title": "Forum für Rückfragen"},
            {"type": "xvid", "ref_id": 900801, "title": "Videoplugin-Objekt"},
            {"type": "wiki", "ref_id": 900951, "title": "Begriffswiki"},
            {"type": "crsr", "ref_id": 900901, "target": 900102, "title": "Verknüpfung Mathematik-Zusatz"},
            {"type": "file", "ref_id": 900303, "title": "Noch nicht freigegeben",
             "props": ["docx", "12 KB"], "offline": True},
        ]),
        ("Sitzungen", 900182, [
            {"type": "sess", "ref_id": 900971, "title": "Sitzung 1: Auftakt"},
        ]),
    ],
    900201: [
        ("Inhalt", None, [
            {"type": "file", "ref_id": 900311, "title": "Blatt 10", "inline": True,
             "props": ["pdf", "203.45 KB", "3. Okt 2026, 09:00"]},
            {"type": "file", "ref_id": 900312, "title": "Blatt 2", "inline": True,
             "props": ["pdf", "180 KB", "2. Okt 2026, 09:00"]},
            {"type": "fold", "ref_id": 900202, "title": "Lösungen"},
        ]),
    ],
    900202: [
        ("Inhalt", None, [
            {"type": "file", "ref_id": 900321, "title": "Lösung Blatt 2", "props": ["pdf", "2,25 MB", "Heute, 09:15"]},
            {"type": "exc", "ref_id": 900521, "title": "Abgabe Lösungen"},
        ]),
    ],
    900203: [
        ("Inhalt", None, [
            {"type": "file", "ref_id": 900331, "title": "Klausur Beispieljahr", "inline": True,
             "props": ["pdf", "1 GB", "6. Feb 2025, 08:20"]},
            {"type": "file", "ref_id": 900332, "title": NFD_TITLE, "props": ["html", "6.8 KB", "22. Sep 2026, 15:41"]},
        ]),
    ],
    900102: [("Inhalt", None, [{"type": "file", "ref_id": 900341, "title": "Organisatorisches",
                                "props": ["pdf", "50 KB", "Gestern, 17:04"]}])],
    900103: [],  # leerer Kurs
    900104: [("Inhalt", None, [])],
    900105: [("Inhalt", None, [{"type": "file", "ref_id": 900351, "title": "Notizen der Gruppe",
                                "props": ["txt", "3 KB", "12. Sep 2026, 14:00"]}])],
    900106: [("Inhalt", None, [{"type": "file", "ref_id": 900361, "title": "Vorlesungsplan Traumwirtschaft",
                                "inline": True, "props": ["pdf", "95.5 KB", "1. Okt 2026, 12:00"]}])],
    900107: [("Inhalt", None, [{"type": "fold", "ref_id": 900211, "title": "Folien Synthesekunde"}])],
    900211: [("Inhalt", None, [{"type": "file", "ref_id": 900371, "title": "Folien Woche 1", "inline": True,
                                "props": ["pdf", "4.02 MB", "29. Sep 2026, 08:30"]}])],
    900108: [("Inhalt", None, [{"type": "webr", "ref_id": 900411, "title": "Videokonferenz-Raum"}])],
    900109: [
        ("Erste Schritte", 900183, [{"type": "webr", "ref_id": 900421, "title": "Lageplan (extern)"}]),
        ("Termine", 900184, [{"type": "file", "ref_id": 900381, "title": "Wochenplan Orientierung", "inline": True,
                              "props": ["pdf", "1.07 MB", "28. Sep 2026, 11:00"]}]),
    ],
}

# Magazin-Wurzel (ref_id=1): Kategorien, nur für den "keine Berechtigung"-Fall (darf nie gecrawlt werden)
ROOT_CATEGORIES = [(900191, "Fakultät für Beispielwissenschaften"), (900192, "Zentrale Testeinrichtungen")]

# Endloser Ordner-Kanal für den Request-Limit-Test: ref 905000+k enthält Ordner 905000+k+1
CHAIN_START = 905000
