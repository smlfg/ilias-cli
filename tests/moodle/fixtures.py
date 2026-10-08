"""Realistische Moodle-4.x-Fixtures für den Fake-Server (nur Testdaten).

Struktur nach `real-fixtures/NOTES.md` und der Moodle-REST-Doku:
* `COURSES`: Antwort von `core_enrol_get_users_courses` (5 Kurse, 3 Semester,
  einer ohne Startdatum, einer ohne `category`, einer `visible: 0`).
* `CONTENTS`: Antwort von `core_course_get_contents` (Abschnitte, Module,
  Ordner mit verschachtelten Unterordnern, PDF-Ressource, URL, Aufgabe, Forum,
  Test, Seite, `label` mit HTML, gesperrtes und verborgenes Modul).

`{base}` wird vom Server durch seine eigene Basis-URL ersetzt, damit die
`fileurl`-Wände so aussehen wie im echten Moodle.
"""

from __future__ import annotations

from urllib.parse import quote

# Zeitstempel (Europe/Berlin) - bewusst hart kodiert, damit die Fixtures stabil sind
TS = {
    "2025-10-01": 1759269600,  # WiSe 2025/26, Start
    "2025-10-15": 1760479200,
    "2025-12-19": 1766098800,
    "2026-01-15": 1768431600,
    "2026-04-10": 1775772000,
    "2026-04-15": 1776204000,  # SoSe 2026, Start
    "2026-04-17": 1776376800,
    "2026-06-15": 1781474400,  # SoSe 2026, Ende
    "2026-07-31": 1785448800,
    "2026-09-30": 1790719200,
    "2026-10-01": 1790805600,  # WiSe 2026/27, Start
    "2026-10-02": 1790892000,
    "2026-10-05": 1791194400,
    "2026-11-15": 1794697200,
    "2026-12-31": 1798671600,
    "2027-02-01": 1801436400,
    "2027-03-30": 1806357600,  # WiSe 2026/27, Ende
}

CATEGORY_PROGRAMMING = 17
CATEGORY_MATHEMATIK = 18

_MODPLURAL = {
    "assign": "Aufgaben",
    "book": "Bücher",
    "choice": "Umfragen",
    "folder": "Verzeichnisse",
    "forum": "Foren",
    "label": "Beschriftungen",
    "lti": "Externe Apps",
    "page": "Seiten",
    "quiz": "Tests",
    "resource": "Dateien",
    "url": "Links",
}


def pluginfile(module: str, instance: int, folder: str, filename: str, *, query: str = "?forcedownload=1") -> str:
    """pluginfile.php-URL wie im echten Moodle (inkl. Kontext- und Instanz-ID)."""
    return (
        "{base}/webservice/pluginfile.php/777/mod_"
        f"{module}/content/{instance}/{quote(folder)}{quote(filename)}{query}"
    )


# --------------------------------------------------------------------- Kurse
COURSES: list[dict] = [
    {
        "id": 51234,
        "shortname": "PR1-WS26",
        "fullname": "Programmieren 1 (WS 2026/27)",
        "displayname": "Programmieren 1 (WS 2026/27)",
        "enrolledusercount": 118,
        "idnumber": "",
        "visible": 1,
        "summary": "<p>Einführung in die Programmierung mit Python.</p>",
        "summaryformat": 1,
        "format": "topics",
        "category": CATEGORY_PROGRAMMING,
        "progress": None,
        "completed": False,
        "startdate": TS["2026-10-01"],
        "enddate": TS["2027-03-30"],
        "lastaccess": TS["2026-10-05"],
        "isfavourite": False,
        "hidden": False,
        "overviewfiles": [],
        "timemodified": TS["2026-09-30"],
    },
    {
        "id": 51240,
        "shortname": "MATH1-SS26",
        "fullname": "Mathematik 1 (SoSe 2026)",
        "displayname": "Mathematik 1 (SoSe 2026)",
        "enrolledusercount": 210,
        "idnumber": "",
        "visible": 1,
        "summary": "<p>Grundlagen der Mathematik: Analysis und lineare Algebra.</p>",
        "summaryformat": 1,
        "format": "topics",
        "category": CATEGORY_MATHEMATIK,
        "progress": None,
        "completed": False,
        "startdate": TS["2026-04-15"],
        "enddate": TS["2026-07-31"],
        "lastaccess": TS["2026-06-15"],
        "isfavourite": True,
        "hidden": False,
        "overviewfiles": [],
        "timemodified": TS["2026-04-10"],
    },
    {
        # zweiter Kurs mit "Mathe" im Titel: mehrdeutige Suche möglich. Sein
        # Kurzname enthält den Kurznamen von 51240, damit eine exakte
        # Kurzname-Suche ("MATH1-SS26") gegen die Teilstring-Suche geprüft
        # werden kann.
        "id": 51241,
        "shortname": "MATH1-SS26-VL",
        "fullname": "Mathematik 2 (SoSe 2026)",
        "displayname": "Mathematik 2 (SoSe 2026)",
        "enrolledusercount": 186,
        "idnumber": "",
        "visible": 1,
        "summary": "<p>Fortsetzung von Mathematik 1.</p>",
        "summaryformat": 1,
        "format": "topics",
        "category": CATEGORY_MATHEMATIK,
        "progress": None,
        "completed": False,
        "startdate": TS["2026-04-17"],
        "enddate": TS["2026-07-31"],
        "lastaccess": TS["2026-06-15"],
        "isfavourite": False,
        "hidden": False,
        "overviewfiles": [],
        "timemodified": TS["2026-04-10"],
    },
    {
        # abgeschlossener Kurs: sichtbar, aber `visible: 0`
        "id": 51100,
        "shortname": "EINS-SEM25",
        "fullname": "Erstsemester-Seminar (WiSe 2025/26)",
        "displayname": "Erstsemester-Seminar (WiSe 2025/26)",
        "enrolledusercount": 64,
        "idnumber": "",
        "visible": 0,
        "summary": "<p>Workshopwoche für Erstsemester.</p>",
        "summaryformat": 1,
        "format": "weeks",
        "category": CATEGORY_PROGRAMMING,
        "progress": None,
        "completed": True,
        "startdate": TS["2025-10-01"],
        "enddate": TS["2025-12-19"],
        "lastaccess": TS["2025-12-19"],
        "isfavourite": False,
        "hidden": False,
        "overviewfiles": [],
        "timemodified": TS["2025-10-01"],
    },
    {
        # ohne Startdatum (`0`) -> Semester unbekannt; `category` fehlt komplett
        "id": 51250,
        "shortname": "SEM-ARBEIT",
        "fullname": "Seminar: Abschlussarbeiten",
        "displayname": "Seminar: Abschlussarbeiten",
        "enrolledusercount": 12,
        "idnumber": "",
        "visible": 1,
        "summary": "<p>Betreuung der Abschlussarbeiten.</p>",
        "summaryformat": 1,
        "format": "topics",
        "progress": None,
        "completed": False,
        "startdate": 0,
        "enddate": 0,
        "lastaccess": TS["2026-01-15"],
        "isfavourite": False,
        "hidden": False,
        "overviewfiles": [],
        "timemodified": TS["2026-01-15"],
    },
]

COURSE_IDS = {
    "PR1-WS26": 51234,
    "MATH1-SS26": 51240,
    "MATH1-SS26-VL": 51241,
    "EINS-SEM25": 51100,
    "SEM-ARBEIT": 51250,
}


# --------------------------------------------------------------------- Inhalte
def _file(name: str, *, path: str = "/", size: int, mimetype: str, module: str, instance: int, sortorder: int = 0, modified: int | None = None):
    stamp = TS["2026-10-02"] if modified is None else modified
    return {
        "type": "file",
        "filename": name,
        "filepath": path,
        "filesize": size,
        "fileurl": pluginfile(module, instance, path, name),
        "timecreated": stamp,
        "timemodified": stamp,
        "sortorder": sortorder,
        "mimetype": mimetype,
        "isexternalfile": False,
        "userid": 4711,
        "author": "Prof. Dr. Beispiel",
        "license": "allrightsreserved",
    }


def _link(url: str, *, name: str = "Link", sortorder: int = 0):
    return {
        "type": "url",
        "filename": name,
        "fileurl": url,
        "timemodified": TS["2026-10-02"],
        "sortorder": sortorder,
        "isexternalfile": True,
        "repositorytype": "url",
    }


def _contents_info(files: list[dict]) -> dict:
    total = sum(int(f.get("filesize") or 0) for f in files if f.get("type") == "file")
    return {
        "filescount": sum(1 for f in files if f.get("type") == "file"),
        "filessize": total,
        "lastmodified": TS["2026-10-02"],
        "mimetypes": sorted({f["mimetype"] for f in files if f.get("type") == "file"}),
        "repositorytype": "",
    }


def _module(
    module_id: int,
    name: str,
    modname: str,
    *,
    instance: int = 1,
    visible: int = 1,
    uservisible: bool = True,
    contents: list[dict] | None = None,
    availabilityinfo: str | None = None,
    with_contentsinfo: bool = False,
):
    module: dict = {
        "id": module_id,
        "url": "{base}/mod/" + modname + "/view.php?id=" + str(module_id),
        "name": name,
        "instance": instance,
        "contextid": 777,
        "visible": visible,
        "uservisible": uservisible,
        "visibleoncoursepage": 1 if visible else 0,
        "modicon": "",
        "modname": modname,
        "modplural": _MODPLURAL.get(modname, modname),
        "indent": 0,
        "noviewlink": False,
        "completion": 0,
    }
    if availabilityinfo:
        module["availabilityinfo"] = availabilityinfo
    if contents is not None:
        module["contents"] = contents
    if with_contentsinfo and contents:
        module["contentsinfo"] = _contents_info(contents)
    return module


def _section(
    section_id: int,
    number: int,
    name: str,
    modules: list[dict],
    *,
    visible: int = 1,
    uservisible: bool = True,
    summary: str = "",
):
    return {
        "id": section_id,
        "name": name,
        "visible": visible,
        "summary": summary,
        "summaryformat": 1,
        "section": number,
        "hiddenbynumsections": 0,
        "uservisible": uservisible,
        "modules": modules,
    }


# --- PR1: der Kurs mit allem, was F3 zeigen soll -----------------------
_PR1_FOLDER_FILES = [
    _file("readme.txt", path="/", size=842, mimetype="text/plain", module="folder", instance=33, sortorder=0),
    _file(
        "blatt01.pdf",
        path="/Blatt 1/",
        size=183456,
        mimetype="application/pdf",
        module="folder",
        instance=33,
        sortorder=1,
        modified=TS["2026-10-05"],
    ),
    _file(
        "blatt02.pdf",
        path="/Blatt 1/",
        size=220480,
        mimetype="application/pdf",
        module="folder",
        instance=33,
        sortorder=2,
        modified=TS["2026-10-05"],
    ),
    _file(
        "musterloesung.pdf",
        path="/Blatt 1/Lösungen/",
        size=421337,
        mimetype="application/pdf",
        module="folder",
        instance=33,
        sortorder=0,
        modified=TS["2026-11-15"],
    ),
    _file(
        "hinweise.pdf",
        path="/Blatt 1/Lösungen/",
        size=12000,
        mimetype="application/pdf",
        module="folder",
        instance=33,
        sortorder=1,
        modified=TS["2026-11-15"],
    ),
    _file(
        "bonus_loesung.pdf",
        path="/Blatt 1/Lösungen/Bonus/",
        size=60000,
        mimetype="application/pdf",
        module="folder",
        instance=33,
        sortorder=0,
        modified=TS["2026-11-15"],
    ),
]

_PR1_ARCHIVE_FILES = [
    _file(
        "klausur_ws25.pdf",
        path="/",
        size=987654,
        mimetype="application/pdf",
        module="folder",
        instance=34,
        sortorder=0,
        modified=TS["2026-01-15"],
    ),
]

CONTENTS: dict[int, list[dict]] = {
    51234: [
        # Abschnitt 0: Standardabschnitt "Allgemeines" ohne Inhalt (leer)
        _section(500, 0, "", []),
        _section(
            501,
            1,
            "Allgemeines",
            [
                _module(9001, "Kursorganisation und Termine", "page"),
                _module(
                    9002,
                    "<p>Liebe Studierende, herzlich willkommen bei Programmieren 1!</p>"
                    "<p>Bitte melden Sie Fragen im Forum &ndash; die Sprechstunde findet "
                    "donnerstags statt.</p>",
                    "label",
                ),
                _module(9003, "Moodle-Wiki zur Vorlesung", "url", contents=[_link("https://example.org/wiki/pr1")]),
            ],
            summary="<p>Organisatorisches zum Kurs.</p>",
        ),
        _section(
            502,
            2,
            "Woche 1: Grundlagen",
            [
                _module(
                    9010,
                    "Übungsblätter",
                    "folder",
                    instance=33,
                    contents=_PR1_FOLDER_FILES,
                    with_contentsinfo=True,
                ),
                _module(
                    9011,
                    "Skript Woche 1",
                    "resource",
                    instance=34,
                    contents=[
                        _file(
                            "skript_woche1.pdf",
                            path="/",
                            size=1048576,
                            mimetype="application/pdf",
                            module="resource",
                            instance=34,
                            modified=TS["2026-10-05"],
                        )
                    ],
                    with_contentsinfo=True,
                ),
                _module(9012, "Woche 1: Folien und Übungsaufgaben", "page"),
                _module(9013, "Fragen zur Woche 1", "forum", instance=35),
            ],
        ),
        _section(
            503,
            3,
            "Prüfungen",
            [
                _module(9020, "Probeklausur", "quiz", instance=36),
                _module(9021, "Abgabe 1: Zahlenratespiel", "assign", instance=37),
                _module(9022, "Fragen & Anregungen zur Klausur", "forum", instance=38),
                # Name mit Rich-Markup-ähnlichen Klammern + verborgen (visible: 0)
                _module(
                    9023,
                    "[Klausur] Altklausuren",
                    "folder",
                    instance=34,
                    visible=0,
                    contents=_PR1_ARCHIVE_FILES,
                    with_contentsinfo=True,
                ),
                # gesperrt: uservisible false, availabilityinfo als HTML, keine contents
                _module(
                    9024,
                    "Nachprüfung",
                    "assign",
                    instance=39,
                    uservisible=False,
                    availabilityinfo=(
                        "<div>Nicht verfügbar, es sei denn: Du bist in der Gruppe "
                        "&bdquo;PoSe&nbsp;1&ldquo; eingeschrieben.</div>"
                    ),
                ),
            ],
        ),
        # Abschnitt für Alt-Inscripten: verborgen und gesperrt
        _section(
            504,
            4,
            "Archiv WiSe 2025/26",
            [
                _module(
                    9030,
                    "Kursarchiv (WiSe 2025/26)",
                    "resource",
                    instance=40,
                    contents=[
                        _file(
                            "archiv_uebersicht.pdf",
                            path="/",
                            size=204800,
                            mimetype="application/pdf",
                            module="resource",
                            instance=40,
                            modified=TS["2026-01-15"],
                        )
                    ],
                    with_contentsinfo=True,
                )
            ],
            visible=0,
            uservisible=False,
        ),
    ],
    51240: [
        _section(
            700,
            1,
            "Mathematik 1",
            [
                _module(9100, "Organisatorisches", "page"),
                _module(9101, "Selbsttest Analysis", "quiz", instance=41),
            ],
        )
    ],
    51241: [_section(800, 1, "Mathematik 2", [_module(9200, "Diskussion zu Woche 1", "forum", instance=42)])],
    51100: [
        _section(
            900,
            1,
            "Erstsemester-Seminar",
            [
                _module(9300, "Rückmeldung zum Seminar", "page"),
                _module(
                    9301,
                    "Exkursion Zoo",
                    "assign",
                    instance=43,
                    uservisible=False,
                    availabilityinfo="<div>Nicht verfügbar, es sei denn: Anmeldung abgeschlossen.</div>",
                ),
            ],
        )
    ],
    # Kurs ohne Inhalt: ein leerer Abschnitt (nur in der JSON-Ausgabe sichtbar)
    51250: [_section(1000, 0, "", [])],
}

UNKNOWN_COURSE = {
    "exception": "moodle_exception",
    "errorcode": "invalidparameter",
    "message": "Course not found",
}
