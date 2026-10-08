"""Fixture-Daten für `ilias courses` (S6): "Meine Kurse und Gruppen" der Fake-HHN.

Alles ausgedacht (ref_ids >= 900101, Kursnummern 990xxx); nur die Struktur folgt den Live-Befunden
(docs/HHN_2FA_SPEC.md §13.1/§13.2). Gerendert von tests/hhn/fake_hhn.py.
"""

from __future__ import annotations

# Mitgliedschaften wie in "Meine Kurse und Gruppen" (Sortierung "Nach Ort": eine
# il-item-group pro übergeordneter Kategorie). props = (Name, Wert) wie
# il-item-property-name/-value; der Name darf leer sein (HHN: "Keine freien Plätze verfügbar").
MEMBERSHIPS: list[dict] = [
    {"ref_id": 900101, "type": "crs", "location": "Fachgruppe Rechenkunst",
     "title": "Mathematik A für Testzwecke (WiSe 2026/27)", "desc": "", "props": [], "offline": False},
    {"ref_id": 900102, "type": "crs", "location": "Fachgruppe Rechenkunst",
     "title": "Mathematik B für Testzwecke", "desc": "",
     "props": [("Zeitraum", "16. Mär 2026 - 31. Aug 2026")], "offline": False},
    {"ref_id": 900103, "type": "crs", "location": "Fachgruppe Protokolle",
     "title": "Einführung in Fantasieprotokolle", "desc": "Synthetischer Beispielkurs ohne Inhalt.",
     "props": [], "offline": False},
    {"ref_id": 900104, "type": "crs", "location": "Archiv",
     "title": "Archivkurs Beispielwissen WS 2025/26", "desc": "", "props": [], "offline": True},
    {"ref_id": 900105, "type": "grp", "location": "Lerngruppen",
     "title": "Lerngruppe Synthese", "desc": "", "props": [], "offline": False},
    # HHN-Titelmuster "<Fach>_<Kürzel>_WS26_27"; Anmeldungsende darf NICHT das Semester bestimmen.
    {"ref_id": 900106, "type": "crs", "location": "Wahlbereich",
     "title": "Traumwirtschaft_Beispiel_WS26_27", "desc": "",
     "props": [("Anmeldungsende", "31. Mär 2027, 12:00"), ("", "Keine freien Plätze verfügbar")], "offline": False},
    # Kursnummer in Klammern im Titel, Semester als "2026 WS".
    {"ref_id": 900107, "type": "crs", "location": "Studiengang Testkunde",
     "title": "TSTB9.1 Synthesekunde (990041) 2026 WS", "desc": "", "props": [], "offline": False},
    # Kursnummer NUR in der Beschreibung, Semester als "WiSe26/27", relative Datumsangabe.
    {"ref_id": 900108, "type": "crs", "location": "Basisphase Beispiel",
     "title": "Beispielökonomie Grundkurs WiSe26/27", "desc": "TS9 SPO9 990077",
     "props": [("Anmeldungsende", "Morgen, 18:30"), ("Freie Plätze", "42")], "offline": False},
    {"ref_id": 900109, "type": "grp", "location": "Orientierung",
     "title": "Orientierungsgruppe 2026 WS", "desc": "", "props": [], "offline": False},
]

# Erwartete Semester (Spec §5.3 + §13)
EXPECTED_SEMESTER = {
    900101: "WiSe 2026/27",  # "(WiSe 2026/27)"
    900102: "SoSe 2026",  # Eigenschaft "Zeitraum" (an der HHN bisher nicht gesehen, generische Regel)
    900103: None,
    900104: "WiSe 2025/26",  # "WS 2025/26"
    900105: None,
    900106: "WiSe 2026/27",  # "_WS26_27" (nicht aus "Anmeldungsende")
    900107: "WiSe 2026/27",  # "2026 WS"
    900108: "WiSe 2026/27",  # "WiSe26/27"
    900109: "WiSe 2026/27",  # "2026 WS"
}

# Favoriten auf dem Dashboard: nur eine Teilmenge -> keine Kursquelle (Spec §13.2)
FAVORITES = [900101, 900105]

# Kursnummern (ausgedacht) -> ref_id; die Nummer steht nur im Titel bzw. in der Beschreibung
COURSE_NUMBERS = {990041: 900107, 990077: 900108}
