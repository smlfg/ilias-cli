"""Tests des Moodle-Login-Teils (login/status/logout).

Kommunikation ausschließlich mit dem lokalen Fake-Moodle aus fake_moodle.py;
jeder Versuch, einen echten Server zu erreichen, lässt den Test scheitern
(siehe conftest.py::no_external_network).

Anforderungen: F1 (Login/Status/Logout), A1 (Passwort), A4 (Token nur im
Keyring/0600-Datei), A5 (Session abgelaufen), N5 (ISO 8601 Europe/Berlin),
N7 (Basis-URL konfigurierbar).
"""
