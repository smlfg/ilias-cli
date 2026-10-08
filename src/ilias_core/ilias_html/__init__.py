"""Reine HTML-Parser für die ILIAS-Seiten (keine I/O, nur ``str`` -> Daten).

Ein Modul pro Seitentyp: ``membership.py`` (Meine Kurse und Gruppen, S6),
``links.py`` (Link-/ref_id-Erkennung, §13.5) und ``props.py``
(Semester/Zahlen/Datum als reine Funktionen). ``fetch.py`` ist die kleine
Lese-Grundlage (GET mit Session, Status-/Redirect-Prüfung, §7), die nur der
ILIAS-Backend benutzt.
"""
