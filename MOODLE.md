# MOODLE.md – Moodle-Login im ilias-cli (Branch `moodle/*`)

Stand: 08.10.2026. Zweck: der Login-Teil (F1) für **Moodle**-Instanzen, zusätzlich zu
ILIAS. Erste Zieldaten: **Hochschule Mannheim** (`https://moodle.hs-mannheim.de`,
Benutzername/Passwort, kein 2FA). Kurse, Dateien und Fristen sind **noch nicht** Scope.

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
```

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

## 4. Exit-Codes (wie INTERFACE.md §3)

| Code | Bedeutung | Moodle-Fall |
|---|---|---|
| 0 | OK | Login/`status`/`logout` erfolgreich |
| 1 | Login fehlgeschlagen | `errorcode` `invalidlogin`/`accessexception`, unbekannte Instanz |
| 2 | nicht eingeloggt | kein Token für diese Instanz gespeichert |
| 3 | Session abgelaufen | `errorcode invalidtoken`; **kein** automatischer Re-Login (A5), der unbrauchbare Token wird lokal gelöscht |
| 4 | Netzwerk/Server | Verbindung fehlgeschlagen, HTTP ≥ 500, Weiterleitung |
| 5 | Parser-Fehler | Antwort ist kein JSON (z. B. HTML-Loginseite), kein Token im JSON |

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

## 7. Tests

```bash
uv run pytest tests/moodle -q     # eigene Suite: lokaler Fake-Moodle auf 127.0.0.1
```

`tests/moodle/fake_moodle.py` bildet beide Endpunkte nach (Schalter für Erfolg,
falsches Passwort, 5xx, HTML, `invalidtoken`, `accessexception`, Fehlertexte mit
Passwort/Token). `tests/moodle/support/sitecustomize.py` blockiert im CLI-Subprozess
alles außer Loopback, die Fixture `no_external_network` zusätzlich im pytest-Prozess:
jeder Versuch, `moodle.hs-mannheim.de` oder einen anderen echten Server zu erreichen,
lässt den Test scheitern. Abgedeckt sind außerdem: Erfolg, falsches Passwort, 5xx,
unerwartetes HTML, `status` ok / `invalidtoken` (3) / ohne Token (2), `logout`,
`--json`-Formen, ISO-8601, Passwort- und Token-Freiheit in Ausgabe und Dateien,
Dateirechte 0600 und Instanz-/Config-Auflösung (ohne Netz).

## 8. Verifikationsstand

Bisher **ausschließlich** gegen den lokalen Fake-Moodle (`tests/moodle/fake_moodle.py`)
verifiziert, nie gegen `moodle.hs-mannheim.de` selbst: es existieren keine echten
Zugangsdaten, und ein Live-Test ist eine eigene Entscheidung des Nutzers (Nutzungsordnung
der Hochschule, §8 N3 der Anforderungen). Der erste echte Lauf gehört in eine separate
REAL_TEST.md-Notiz, wie auf `feature/saml-uni-mannheim`.

## 9. `ilias courses` (F2) und `ilias ls` (F3)

```bash
ilias courses [--instance X] [--json]
ilias ls <kurs> [--instance X] [--depth N] [--json]
```

### Kurse

Ablauf: gespeicherter Token → `core_webservice_get_site_info` (liefert `userid`) →
`core_enrol_get_users_courses` mit `userid=<id>`. `<kurs>` bei `ls` ist eine numerische
Kurs-ID oder ein eindeutiger Teilstring von Kurz-/Langname (Klein-/Großschreibung egal);
ein exakter Kurz- oder Langname schlägt Teilstrings. Kein Treffer → Exit 1,
`error.code = "course_not_found"`; mehrere Treffer → Exit 1, `"course_ambiguous"` mit
`error.candidates = [{"id", "shortname", "fullname"}, …]` und einer Kandidatenliste in
der Fehlermeldung. Kurs → Inhalte via `core_course_get_contents` mit `courseid=<id>`.

Semester-Label aus `startdate` (Europe/Berlin): Apr–Sep `"SoSe YYYY"`, Okt–Dez
`"WiSe YYYY/YY+1"`, Jan–Mär `"WiSe YYYY-1/YY"`; `startdate` 0/fehlend → `null`.

`--json` für `courses` – genau ein Objekt:

```json
{"instance": "hs-mannheim", "lms": "moodle", "count": 2,
 "courses": [{"id": 1234, "fullname": "…", "shortname": "…", "category": 17,
              "semester": "WiSe 2026/27", "visible": true,
              "startdate": "2026-10-01T02:00:00+02:00", "enddate": null,
              "url": "https://…/course/view.php?id=1234"}],
 "timestamp": "…"}
```

Text-Ausgabe: Rich-Tabelle (ID, Kurzname, Name, Semester), sortiert nach Semester
(neuestes zuerst, `null` zuletzt), dann Name.

### ls: Baum des Kurses

`--depth N`: 1 = Abschnitte, 2 = +Module, 3 = +Dateien/erste Ordner­ebene, jede weitere
Ebene ein Ordner­level mehr. Standard: unbegrenzt. `N < 1` → Usage-Fehler (Exit 2).

Modul-Ordner (`modname == "folder"`) werden aus den `filepath`-Angaben der `contents`
ausgerollt (`/`, `/Blatt 1/`, `/Blatt 1/Lösungen/` → verschachtelte Ordner). `resource`
zeigt seine Dateien, `url` das Ziel-URL, alle anderen Module (`assign`, `forum`,
`quiz`, `page`, `label`, `choice`, …) sind Blätter mit Typ-Icon. Module/Abschnitte
mit `uservisible: false` stehen weiter in der Liste, markiert `[gesperrt]` plus
HTML-bereinigtem `availabilityinfo`; `visible: 0` → `[verborgen]`. `label`-Module
zeigen den HTML-befreiten Name (max. 60 Zeichen). Leere Abschnitte ohne Namen werden
in der Text-Ansicht weggelassen, im JSON bleiben sie enthalten. Rich-Markup in
serverseitigen Strings wird escaped.

`--json` für `ls` – genau ein Objekt:

```json
{"instance": "hs-mannheim", "lms": "moodle",
 "course": {"id": 1234, "fullname": "…", "shortname": "…"},
 "depth": null,
 "sections": [{"id": 501, "number": 0, "name": "Allgemeines", "visible": true,
   "uservisible": true,
   "modules": [{"id": 9010, "name": "Übungsblätter", "modname": "folder",
     "url": "https://…/mod/folder/view.php?id=9010", "visible": true,
     "uservisible": true, "availability": null,
     "children": [{"type": "folder", "name": "Blatt 1", "path": "/Blatt 1/",
                   "children": [{"type": "file", "name": "blatt01.pdf",
                                 "path": "/Blatt 1/", "size": 183456,
                                 "mimetype": "application/pdf",
                                 "timemodified": "2026-10-15T02:00:00+02:00",
                                 "fileurl": "https://…/pluginfile.php/…"}]}]}]}],
 "timestamp": "…"}
```

Knoten-Typen unter `children`: `{"type": "folder", "name", "path", "children": […]}` ·
`{"type": "file", "name", "path", "size", "mimetype", "timemodified", "fileurl"}` ·
`{"type": "url", "name", "url"}`. `fileurl` enthält niemals den Token (Downloads sind F5).

Beispiel-Text-Baum (Fake-Fixtures, `ilias ls 1234`):

```
Mathe 1 (WS 2026/27) (MA1-WS26) #1234
├── 📂 Allgemeines
│   ├── 🔗 Kursseite
│   │   └── 🔗 FH-Portal → https://www.example.edu/fh
│   ├── 💬 Ankündigungen
│   └── 🏷️ Herzlich willkommen im Kurs!
├── 📂 Übungen
│   ├── 📁 Übungsblätter
│   │   ├── 📁 Blatt 1
│   │   │   ├── 📁 Lösungen
│   │   │   │   └── 📄 blatt01_lsg.pdf (93 KB)
│   │   │   └── 📄 blatt01.pdf (179 KB)
│   │   └── 📁 Blatt 2
│   │       └── 📄 blatt02.pdf (254 KB)
│   ├── 📝 Hausaufgabe 1
│   └── ❓ Probeklausur [verborgen]
├── 📂 Material
│   ├── 📄 Skript.pdf
│   │   └── 📄 Skript.pdf (4.0 MB)
│   ├── 📃 Kursübersicht
│   ├── 📊 Terminumfrage
│   └── 📁 [Klausur] Altklausuren
│       └── 📁 2025
│           └── 📄 klausur2025.pdf (512 KB)
└── 📂 Prüfungsorganisation
    └── 📝 Abschlussprojekt [gesperrt] – Nicht verfügbar, es sei denn: …
```

(Icons: 📁 Ordner, 📄 Datei mit Größe, 📝 Aufgabe, 💬 Forum, 🔗 Link, ❓ Test,
📃 Seite, 📊 Abstimmung; unbekannte Module: 🔹 mit Modname.)

Fehler- und Exit-Codes entsprechen Abschnitt 4 (`course_not_found`/`course_ambiguous`
→ 1, `not_logged_in` → 2, `session_expired` → 3, Netzwerk/5xx → 4, Parser → 5).
Für das ILIAS-Backend werfen `courses`/`ls` einen klaren
`NotSupportedError` ("für ILIAS noch nicht implementiert", Exit 1).

### Tokens und Sicherheit

Der Token wird ausschließlich als Formularfeld `wstoken` im POST-Body an
`/webservice/rest/server.php` gesendet – nie in der URL/Query. Ausgabe (Text,
`--json`, stderr) und gespeicherte Dateien enthalten nie den Token.

## 10. Noch offen

Dateien herunterladen (F5), Fristen (F4), Sync (F6) für Moodle fehlen; der
ILIAS-Login (OIDC/Keycloak + TOTP) ist in diesem Branch weiterhin nur ein
Platzhalter (Exit 1), `status`/`logout` funktionieren dort, weil der
Session-Speicher backend-unabhängig ist.