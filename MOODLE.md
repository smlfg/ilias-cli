# MOODLE.md – Moodle im ilias-cli (Branch `moodle/*`)

Stand: 08.10.2026. Zweck: Login (F1) sowie Kurse/Dateibäume (F2/F3) für
**Moodle**-Instanzen, zusätzlich zu ILIAS. Erste Zieldaten: **Hochschule
Mannheim** (`https://moodle.hs-mannheim.de`, Benutzername/Passwort, kein 2FA).
Fristen, Abgaben und Downloads (F4/F5) sind **noch nicht** Scope.

Grundlage der Endpunkte: `real-fixtures/NOTES.md`, Abschnitt „HS Mannheim Moodle"
(anonym geprüft am 08.10.2026, ohne Zugangsdaten):
`enablewebservices = 1`, `enablemobilewebservice = 1`, `typeoflogin = 1`
(Benutzername/Passwort), keine Identity Provider, kein 2FA.

## 1. Aufruf

```bash
ilias login  --instance hs-mannheim      # fragt Benutzername, dann Passwort (verdeckt)
ilias status --instance hs-mannheim      # Exit 0 = Session gültig
ilias logout --instance hs-mannheim      # löscht den Token lokal, immer Exit 0
ilias status --instance hs-mannheim --json
ilias courses --instance hs-mannheim [--json]          # F2: eigene Kurse
ilias ls <kurs> --instance hs-mannheim [--depth N] [--json]  # F3: Kursbaum
```

`<kurs>` ist eine numerische Kurs-Id oder ein case-insensitiver Teilstring von
Kurzname/Name. Ein exakter (case-insensitiver) Kurzname/Name gewinnt über
Teilstring-Treffer. Kein Treffer → Exit 1 (`course_not_found`), mehrere Treffer →
Exit 1 mit Kandidatenliste (`course_ambiguous`, in `--json` als
`"candidates": [{id, shortname, fullname}]`). `--depth N`: 1 = nur Abschnitte,
2 = + Bausteine, 3 = + Dateien/erste Ordnerebene, jede weitere Stufe eine
Unterordnerebene mehr (Default: unbegrenzt); N < 1 → Usage-Fehler (Exit 2).

Ohne `--instance` gilt `instance` aus `config.toml`. Ohne config.toml ist ILIAS/HHN
die Default-Instanz, damit bestehende ILIAS-Aufrufe unverändert bleiben.

## 2. Konfiguration

Datei `$ILIAS_CLI_CONFIG_DIR/config.toml`, sonst `~/.config/ilias-cli/config.toml`.

```toml
instance = "hs-mannheim"          # Vorgabe, wenn --instance fehlt

[instances.hs-mannheim]
lms = "moodle"                    # "moodle" | "ilias" (Default)
base_url = "https://moodle.hs-mannheim.de"

[instances.hhn]                   # weitere Hochschule
lms = "ilias"
base_url = "https://ilias.hs-heilbronn.de"
client_id = "iliashhn"
```

Eingebaute Profile (Startwerte, in `config.toml` überschreibbar – N7):

| Key | lms | base_url |
|---|---|---|
| `hs-mannheim` | `moodle` | `https://moodle.hs-mannheim.de` |
| `hhn` | `ilias` | `https://ilias.hs-heilbronn.de` (client_id `iliashhn`) |

Die flache Form (`base_url`/`client_id` oben in der Datei) beschreibt weiterhin die
ILIAS-Default-Instanz und wird von den ILIAS-Akzeptanztests benutzt.

## 3. HTTP-Flow

1. `POST {base}/login/token.php` mit `username`, `password`, `service=moodle_mobile_app`
   * Erfolg `200` → `{"token": "...", "privatetoken": null}`
   * Abgelehnt → `{"error": "Invalid login, please try again", "errorcode": "invalidlogin"}`
2. **Verifikation** `POST {base}/webservice/rest/server.php` mit
   `wstoken`, `wsfunction=core_webservice_get_site_info`, `moodlewsrestformat=json`
   * Erfolg → `{"sitename", "username", "fullname", "userid", "release", "lang", ...}`
   * Token ungültig → `{"exception": "moodle_exception", "errorcode": "invalidtoken", ...}`
3. **Erst danach** wird der Token gespeichert und Erfolg gemeldet. `status` ruft nur
   Schritt 2 mit dem gespeicherten Token auf.

Eigener User-Agent `ilias-cli/<version>` (N2), `follow_redirects=False` und
`trust_env=False`: keine Weiterleitungen, keine Proxies aus der Umgebung – Zugangsdaten
und Token bleiben auf diesem Rechner. Netzwerkfehler bei der Statusprüfung werden einmal
mit Backoff wiederholt, der Login-POST nie (kein zweiter Anmeldeversuch).

## 3b. Kurse und Inhalte (F2/F3, nur Moodle)

Flows (Token immer im POST-Body, nie in der URL):

* F2 `courses`: gespeicherter Token → `core_webservice_get_site_info` (liefert
  `userid`) → `core_enrol_get_users_courses` mit `userid`.
* F3 `ls`: Kurs per Id/Teilstring auflösen (über die F2-Kursliste, Logik in
  `ilias_core.service.resolve_course`), dann `core_course_get_contents` mit `courseid`.

Semester (`semester`): aus `startdate` in Europe/Berlin – Apr–Sep → `"SoSe YYYY"`,
Okt–Dez → `"WiSe YYYY/YY+1"`, Jan–Mär → `"WiSe YYYY-1/YY"` (z. B. 2026-10-01 →
`"WiSe 2026/27"`, 2027-02-01 → `"WiSe 2026/27"`); startdate 0/fehlend → `null`.
Sortierung: neuestes Semester zuerst, ohne Semester ans Ende, dann Name (A–Z).

Baum (Kurs → Abschnitte → Bausteine → Dateien/Ordner/Links): `folder`-Module
werden anhand von `filepath` (`/`, `/Blatt 1/`, `/Blatt 1/Lösungen/`, …) zu
verschachtelten Ordnern; `resource` zeigt seine Datei(en), `url` das Linkziel;
`assign`/`forum`/`quiz`/`page`/`label`/`choice`/`lti`/… sind Blätter mit
Typkennzeichnung. Markierungen: `uservisible == false` → `[gesperrt]` plus
`availabilityinfo` als Klartext (HTML entfernt), `visible == 0` → `[verborgen]`;
`label` zeigt Kurztext (HTML entfernt, max. 60 Zeichen + `…`). Leere Abschnitte
ohne Namen erscheinen nur im JSON, nicht in der Menschenansicht. Serverstrings
werden Rich-maskiert (z. B. `[Klausur]` bleibt wörtlich). Datei-URLs enthalten
nie den Token (Download ist F5, nicht hier).

Beispiel (Fake-Fixture, `ilias ls 101 --instance hs-mannheim`):

```text
📚 Mathematik 1 (WS 2026/27)
├── § Allgemeines
│   ├── 🏷️ Willkommen zur Mathematik 1 Übung und Organisatorisches für… [Text]
│   ├── 💬 Ankündigungen [Forum]
│   └── 🔗 Skript-Webseite [Link]
│       └── 🔗 Skript-Webseite → https://example.org/mathe-skript
├── § Übungsblätter
│   ├── 📁 Übungsblätter [Ordner]
│   │   ├── 📁 Blatt 1 [Ordner]
│   │   │   ├── 📁 Lösungen [Ordner]
│   │   │   │   └── 📄 loesung01.pdf (94.2 KB)
│   │   │   └── 📄 blatt01.pdf (179 KB)
│   │   ├── 📁 [Klausur] Altklausuren [Ordner]
│   │   │   └── 📄 klausur_ws25.pdf (500 KB)
│   │   └── 📄 blatt00.pdf (41.1 KB)
│   ├── 📄 Merkblatt Übung (mit Ümläuten äöü) [Datei]
│   │   └── 📄 merkblatt.pdf (179 KB)
│   ├── 📝 Abgabe Blatt 1 [Aufgabe] [gesperrt] (Nicht verfügbar, es sei denn: Es ist nach dem 1. Oktober 2026)
│   └── ❓ Test: Grundlagen [Test] [verborgen]
└── § Vorlesung
    ├── 📃 Lernziele & Überblick [Seite]
    └── 🗳️ Umfrage [Termine] [Abstimmung] [gesperrt] (Nur für Gruppe A sichtbar.)
```

## 4. Exit-Codes (wie INTERFACE.md §3)

| Code | Bedeutung | Moodle-Fall |
|---|---|---|
| 0 | OK | Login/`status`/`logout`/`courses`/`ls` erfolgreich |
| 1 | Login fehlgeschlagen | `errorcode` `invalidlogin`/`accessexception`, unbekannte Instanz |
| 1 | sonstiger Fehler | `course_not_found` (kein Kurs passt), `course_ambiguous` (mehrere passen, mit Kandidaten), `not_supported` (F2/F3 auf ILIAS: „für ILIAS noch nicht implementiert“) |
| 2 | nicht eingeloggt | kein Token für diese Instanz gespeichert |
| 3 | Session abgelaufen | `errorcode invalidtoken`; **kein** automatischer Re-Login (A5), der unbrauchbare Token wird lokal gelöscht |
| 4 | Netzwerk/Server | Verbindung fehlgeschlagen, HTTP ≥ 500, Weiterleitung |
| 5 | Parser-Fehler | Antwort ist kein JSON (z. B. HTML-Loginseite), kein Token im JSON, Liste statt Objekt (und umgekehrt), fehlende Pflichtfelder |

## 5. Sicherheit (A1, A4, N1)

* **Passwort**: kein `--password`-Flag. Eingabe nur verdeckt (`getpass` bei TTY) oder als
  Zeile von stdin; Prompts gehen nach **stderr**, damit `--json` auf stdout genau ein
  JSON-Objekt bleibt. Das Passwort steckt in `ilias_core.secrets.Secret`
  (`repr()`/`str()` = `***`) und wird nie gespeichert, geloggt oder in Fehlermeldungen
  ausgegeben – auch dann nicht, wenn der Server es in einer Fehlermeldung zurückspiegelt.
* **Token**: pro Instanz im OS-Schlüsselbund (`keyring`), sonst in
  `<config-dir>/sessions/<instance>.json`, das **von Anfang an** mit `os.open(…, 0o600)`
  (Verzeichnis `0700`) angelegt wird. Nie im Arbeitsverzeichnis, nie im JSON-Output, nie
  im Log. `logout` löscht Keyring **und** Datei.
* **Unerwartete Ausnahmen** werden nur als Typname gemeldet, ohne Traceback – ein
  Traceback könnte Werte lokaler Variablen enthalten.

## 6. `--json`

Erfolg (ein Objekt auf stdout):

```json
{"ok": true, "command": "status", "instance": "hs-mannheim", "lms": "moodle",
 "base_url": "https://moodle.hs-mannheim.de", "username": "s12345", "fullname": "…",
 "sitename": "Lernplattform TH-MA", "userid": 42, "logged_in": true,
 "timestamp": "2026-10-08T09:12:33+02:00"}
```

Fehler: `{"ok": false, "command": …, "instance": …, "error": {"code": "session_expired",
"message": …, "hint": …}, "exit_code": 3, "timestamp": "…"}` – der Exit-Code bleibt
zusätzlich der Prozess-Exit-Code. Zeitstempel sind ISO 8601 in Europe/Berlin (N5).

`courses --json` (genau ein Objekt auf stdout):

```json
{"ok": true, "command": "courses", "instance": "hs-mannheim", "lms": "moodle",
 "count": 4,
 "courses": [{"id": 101, "fullname": "Mathematik 1 (WS 2026/27)",
              "shortname": "MATHE-WS26", "category": 17, "semester": "WiSe 2026/27",
              "visible": true, "startdate": "2026-10-01T10:00:00+02:00",
              "enddate": "2027-03-31T23:59:00+02:00",
              "url": "https://moodle.hs-mannheim.de/course/view.php?id=101"}, …],
 "timestamp": "2026-10-08T09:12:33+02:00"}
```

`ls --json` (verschachtelt; leere Abschnitte und `depth` bleiben erhalten):

```json
{"ok": true, "command": "ls", "instance": "hs-mannheim", "lms": "moodle",
 "course": {"id": 101, "shortname": "MATHE-WS26", "fullname": "Mathematik 1 (WS 2026/27)"},
 "depth": null,
 "sections": [{"id": 501, "number": 0, "name": "Allgemeines",
               "visible": true, "uservisible": true,
               "modules": [{"id": 9103, "name": "Skript-Webseite", "modname": "url",
                            "url": "https://…/mod/url/view.php?id=9103",
                            "visible": true, "uservisible": true, "availability": null,
                            "children": [{"type": "url", "name": "Skript-Webseite",
                                          "url": "https://example.org/mathe-skript"}]}, …]}],
 "timestamp": "2026-10-08T09:12:33+02:00"}
```

Knotentypen: `{"type": "folder", "name", "path", "children": […]}` |
`{"type": "file", "name", "path", "size", "mimetype", "timemodified"` (ISO),
`"fileurl"}` | `{"type": "url", "name", "url"}`. Fehler mit Kandidaten:
`{"ok": false, "command": "ls", "error": {"code": "course_ambiguous",
"message": "Mehrere Kurse passen zu 'mathe': …",
"candidates": [{"id": 101, …}, {"id": 102, …}]}, "exit_code": 1, …}`.

## 7. Tests

```bash
uv run pytest tests/moodle -q     # eigene Suite: lokaler Fake-Moodle auf 127.0.0.1
```

`tests/moodle/fake_moodle.py` bildet alle benutzten Endpunkte nach (Schalter für Erfolg,
falsches Passwort, 5xx, HTML, `invalidtoken`, `accessexception`, Fehlertexte mit
Passwort/Token, leere Kursliste). Fixtures: 4 Kurse (zwei Semester WiSe 2026/27 +
SoSe 2026, einer mit startdate 0/ohne Kategorie/verborgen; zwei „mathe“-Kurse für
Ambiguität), Kurs 101 mit 4 Abschnitten (inkl. leerem), Ordner mit 2
Unterordnerebenen + `[Klausur]`-Name, PDF-Ressource, URL-, Aufgabe-, Forum-,
Test-, Seite-, Abstimmung- und HTML-Label-Module, ein `uservisible: false`-Modul
mit `availabilityinfo` und ein `visible: 0`-Modul.
`tests/moodle/support/sitecustomize.py` blockiert im CLI-Subprozess
alles außer Loopback, die Fixture `no_external_network` zusätzlich im pytest-Prozess:
jeder Versuch, `moodle.hs-mannheim.de` oder einen anderen echten Server zu erreichen,
lässt den Test scheitern. Abgedeckt sind außerdem: Erfolg, falsches Passwort, 5xx,
unerwartetes HTML, `status` ok / `invalidtoken` (3) / ohne Token (2), `logout`,
`courses`-/`ls`-Formen (human + `--json`), Semesterableitung (inkl. Jan–Mär-Fall),
Kursauflösung (Id/Teilstring/exakt-gewinnt/mehrdeutig/nicht-gefunden),
`--depth`-Stufen, Ordnernestung aus `filepath`, Sichtbarkeitsmarker, Label-Kürzung,
Rich-Maskierung, Token-Freiheit in Ausgabe/URLs/Dateien, POST-Body-statt-URL für
`wstoken`, `--json`-Formen, ISO-8601, Passwort- und Token-Freiheit in Ausgabe und Dateien,
Dateirechte 0600 und Instanz-/Config-Auflösung (ohne Netz).

## 8. Verifikationsstand

Bisher **ausschließlich** gegen den lokalen Fake-Moodle (`tests/moodle/fake_moodle.py`)
verifiziert, nie gegen `moodle.hs-mannheim.de` selbst: es existieren keine echten
Zugangsdaten, und ein Live-Test ist eine eigene Entscheidung des Nutzers (Nutzungsordnung
der Hochschule, §8 N3 der Anforderungen). Der erste echte Lauf gehört in eine separate
REAL_TEST.md-Notiz, wie auf `feature/saml-uni-mannheim`.

## 9. Noch offen

Fristen, Abgaben und Downloads (F4/F5) für Moodle fehlen; der ILIAS-Login
(OIDC/Keycloak + TOTP) ist in diesem Branch weiterhin nur ein Platzhalter
(Exit 1), `status`/`logout` funktionieren dort, weil der Session-Speicher
backend-unabhängig ist. Auch F2/F3 melden auf ILIAS klar „für ILIAS noch nicht
implementiert“ (Exit 1, `not_supported`).