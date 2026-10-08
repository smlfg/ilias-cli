# MOODLE.md – Moodle im ilias-cli (Branch `moodle/*`)

Stand: 08.10.2026. Zweck: **Login (F1)** und die **Kursliste (F2)** / **Kursinhalt (F3)**
für **Moodle**-Instanzen, zusätzlich zu ILIAS. Erste Zieldaten: **Hochschule Mannheim**
(`https://moodle.hs-mannheim.de`, Benutzername/Passwort, kein 2FA). Downloads, Fristen
und Abgaben (F4–F7) sind **noch nicht** Scope.

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

ilias courses --instance hs-mannheim                  # eigene Kurse (Tabelle)
ilias courses --instance hs-mannheim --json           # Kursliste als JSON
ilias ls PR1 --instance hs-mannheim                   # Kursbaum (ID oder Teilstring)
ilias ls 101 --instance hs-mannheim --depth 2         # nur Abschnitte + Module
ilias ls "PR1-WS26" --instance hs-mannheim --json     # Baum als JSON
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

## 3a. F2/F3 – `courses` und `ls`

Beide Befehle nutzen den gespeicherten Token (wie `status`) und **setzen den Token
immer in den POST-Body** (`wstoken`), nie in die URL. Fehlt der Token → Exit 2.

### `ilias courses`

1. `core_webservice_get_site_info` → `userid`
2. `core_enrol_get_users_courses` mit `userid` → Kursliste

Pro Kurs: `id`, `fullname`, `shortname`, `category` (int oder null), `semester`,
`visible` (bool), `startdate`/`enddate` (ISO 8601 Europe/Berlin oder null bei 0/fehlend),
`url` = `{base}/course/view.php?id=<id>`.

`semester` wird aus `startdate` in Europe/Berlin abgeleitet (reine Funktion
`timeutil.semester_from_timestamp`): Mrz–Aug → `SoSe YYYY`, Sep–Dez → `WiSe YYYY/YY+1`,
Jan–Feb → `WiSe YYYY-1/YY`; `0`/fehlend → `null`. Die Menschen-Tabelle (ID, Kurzname,
Name, Semester) sortiert nach Semester (neuestes zuerst, `null` zuletzt), dann Name.

### `ilias ls <kurs> [--depth N]`

1. Kurs auflösen über die Kursliste: numerische Eingabe ist eine Kurs-ID, sonst ein
   **case-insensitiver Teilstring** von `fullname`/`shortname`. Ein exakter Kurzname/Name
   schlägt einen bloßen Teilstring. Kein Treffer → Exit 1 `course_not_found`; mehrere →
   Exit 1 `course_ambiguous` (Kandidaten in der Meldung und, mit `--json`, als
   `error.candidates`).
2. `core_course_get_contents` mit `courseid` → Abschnitte → Module → Dateien.

`folder`-Module werden anhand `filepath` (z. B. `/`, `/Blatt 1/`, `/Blatt 1/Lösungen/`)
zu verschachtelten Ordnerknoten; `resource`-Module zeigen ihre Datei(en); `url`-Module
den Link; alle anderen Module (`assign`, `forum`, `quiz`, `page`, `label`, `choice`,
`lti`, …) sind Blattknoten mit Typ-Label. `label`-Namen werden von HTML befreit und auf
60 Zeichen gekürzt. `uservisible == false` wird `[gesperrt]` markiert (mit
HTML-befreitem `availabilityinfo`), `visible == 0` mit `[verborgen]`. Leere
Standardabschnitte fehlen im Menschen-Text, stehen aber im JSON.

`--depth N`: `1` = Abschnitte, `2` = +Module, `3` = +Dateien/erste Ordnerebene, jede
weitere Ebene = eine weitere Unterordnerebene. Default: unbegrenzt. `N < 1` ist ein
Usage-Fehler (Exit 2).

### Beispielbaum (aus den Fake-Fixtures, `ilias ls 101`)

```
Programmieren 1 (WS 2026/27) (PR1-WS26)
├── Allgemeines
│   ├── 📁 Ordner: Übungsblätter
│   │   ├── 📁 Blatt 1
│   │   │   ├── 📁 Lösungen
│   │   │   │   └── 📄 loesung1.md (4.0 KB)
│   │   │   └── 📄 aufgabe1.pdf (50.0 KB)
│   │   ├── 📁 Blatt 2
│   │   │   └── 📄 blatt02.pdf (200.0 KB)
│   │   └── 📄 blatt01.pdf (179.2 KB)
│   ├── 🔗 Openbook Rheinwerk: C von A bis Z & Dienste → https://openbook.rheinwerk-verlag.de/…(vollständige URL)
│   └── 🏷️ Beschriftung: Willkommen im Kurs Bitte alles lesen
├── Übung 1
│   ├── 📄 Datei: Skript Kapitel 1
│   ├── 📝 Aufgabe: Aufgabe 1
│   ├── 💬 Forum: Fragenforum
│   ├── 📅 Terminplaner: Sprechstunde
│   └── 📋 Feedback: Rückmeldung
└── Altklausuren --> Archiv & Mehr
    ├── 📁 Ordner: [Klausur] Altklausuren
    ├── ❓ Test: Probeklausur [verborgen]
    ├── 🗳️ Abstimmung: Evaluation [gesperrt] (Nicht verfügbar, es sei denn: Einschreibung)
    ├── 📃 Seite: Lernziele
    └── 📁 Ordner: Natursortierung
        ├── 📄 Blatt1.pdf (1.0 KB)
        ├── 📄 blatt2.pdf (1.0 KB)
        ├── 📄 blatt10.pdf (1.0 KB)
        └── 📄 Blatt&1info.pdf (1.0 KB)
```

Hinweise: `url`-Module erscheinen als genau eine Zeile `🔗 <Modulname> → <URL>` (der
Modulname trägt die Satzzeichen, der Dateiname aus `contents` ist von Moodle beschnitten);
URLs werden nie abgeschnitten. HTML-Entities (`&gt;`, `&amp;`) werden in der Kernschicht
dekodiert, Dateien in Ordnern natürlich und case-insensitive sortiert (`blatt2` vor
`blatt10`).

### JSON-Formen

`ilias courses --json` (genau ein Objekt):

```json
{"instance": "hs-mannheim", "lms": "moodle", "count": 5,
 "courses": [{"id": 101, "fullname": "Programmieren 1 (WS 2026/27)",
   "shortname": "PR1-WS26", "category": 17, "semester": "WiSe 2026/27",
   "visible": true, "startdate": "2026-10-01T00:00:00+02:00",
   "enddate": "2027-03-31T00:00:00+02:00",
   "url": "https://moodle.hs-mannheim.de/course/view.php?id=101"}],
 "timestamp": "2026-10-08T09:12:33+02:00"}
```

`ilias ls <kurs> --json` (verschachtelt):

```json
{"instance": "hs-mannheim", "lms": "moodle",
 "course": {"id": 101, "fullname": "Programmieren 1 (WS 2026/27)", "shortname": "PR1-WS26"},
 "depth": null,
 "sections": [{"id": 501, "number": 0, "name": "Allgemeines", "visible": true,
   "uservisible": true, "modules": [{"id": 9001, "name": "Übungsblätter",
     "modname": "folder", "url": "https://…/mod/folder/view.php?id=9001",
     "visible": true, "uservisible": true, "availability": null,
     "children": [
       {"type": "folder", "name": "Blatt 1", "path": "/Blatt 1/", "children": [
         {"type": "file", "name": "aufgabe1.pdf", "path": "/Blatt 1/",
          "size": 51200, "mimetype": "application/pdf",
          "timemodified": "2026-10-02T07:46:40+02:00",
          "fileurl": "https://…/pluginfile.php/777/mod_folder/content/0/Blatt%201/aufgabe1.pdf?forcedownload=1"}]},
       {"type": "file", "name": "blatt01.pdf", "path": "/", "size": 183456,
        "mimetype": "application/pdf", "timemodified": "2026-10-02T02:13:20+02:00",
        "fileurl": "https://…/pluginfile.php/777/mod_folder/content/0/blatt01.pdf?forcedownload=1"}]},
     {"type": "url", "name": "Moodle-Doku", "url": "https://docs.moodle.org/"}]}],
 "timestamp": "2026-10-08T09:12:33+02:00"}
```

`error.candidates` (nur bei `course_ambiguous`): `[{"id", "fullname", "shortname"}, …]`.

Der Token wird **nie** an `fileurl` oder eine andere URL angehängt (Download ist F5)
und erscheint nie in stdout/stderr/JSON.

## 4. Exit-Codes (wie INTERFACE.md §3)

| Code | Bedeutung | Moodle-Fall |
|---|---|---|
| 0 | OK | Login/`status`/`logout` erfolgreich |
| 1 | Login fehlgeschlagen / Kursauflösung | `errorcode` `invalidlogin`/`accessexception`, unbekannte Instanz; `ls`: `course_not_found` / `course_ambiguous` |
| 2 | nicht eingeloggt | kein Token für diese Instanz gespeichert (auch für `courses`/`ls`) |
| 3 | Session abgelaufen | `errorcode invalidtoken`; **kein** automatischer Re-Login (A5), der unbrauchbare Token wird lokal gelöscht |
| 4 | Netzwerk/Server | Verbindung fehlgeschlagen, HTTP ≥ 500, Weiterleitung |
| 5 | Parser-Fehler | Antwort ist kein JSON (z. B. HTML-Loginseite), fehlende Felder (`userid`, kein Array) |

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

`tests/moodle/fake_moodle.py` bildet die Endpunkte nach (Schalter für Erfolg,
falsches Passwort, 5xx, HTML, `invalidtoken`, `accessexception`, Fehlertexte mit
Passwort/Token) und liefert realistische Kurs-Fixtures: fünf Kurse (zwei Semester,
einer ohne `startdate`, `visible: 0`, zwei Treffer für „mathe"), einen Kurs mit vier
Abschnitten (inkl. leerem), verschachtelte Ordner (≥ 2 Ebenen), PDF-Ressource,
`url`-, `assign`-, `forum`-, `quiz`-, `label`-Modul, `uservisible: false` mit
`availabilityinfo`, verstecktes Modul, Umlaute und `[Klausur] Altklausuren`.
`tests/moodle/support/sitecustomize.py` blockiert im CLI-Subprozess alles außer
Loopback, die Fixture `no_external_network` zusätzlich im pytest-Prozess: jeder Versuch,
`moodle.hs-mannheim.de` oder einen anderen echten Server zu erreichen, lässt den Test
scheitern.

Abgedeckt sind: Login/Status/Logout (Erfolg, falsches Passwort, 5xx, HTML,
`invalidtoken`, ohne Token), `courses` (Tabelle und JSON-Form, Semesterableitung als
Unit-Test inkl. Jan–Mär, Sortierung, Attribute), `ls` (per ID, Teilstring,
exakter-Kurzname-gewinnt, mehrdeutig mit Kandidaten, nicht gefunden, `--depth 1–5`,
verschachtelte `filepath`-Struktur, Sichtbarkeits-/Versteckt-Marker,
Label-HTML-Bereinigung, literales Rich-Markup), Token-Freiheit in Ausgabe/URLs,
`wstoken` nur im POST-Body (nie im Query) sowie der ILIAS-`NotSupported`-Fehler.

## 8. Verifikationsstand

Bisher **ausschließlich** gegen den lokalen Fake-Moodle (`tests/moodle/fake_moodle.py`)
verifiziert, nie gegen `moodle.hs-mannheim.de` selbst: es existieren keine echten
Zugangsdaten, und ein Live-Test ist eine eigene Entscheidung des Nutzers (Nutzungsordnung
der Hochschule, §8 N3 der Anforderungen). Der erste echte Lauf gehört in eine separate
REAL_TEST.md-Notiz, wie auf `feature/saml-uni-mannheim`.

## 9. Noch offen

Downloads, Fristen, Abgaben (F4–F7) für Moodle fehlen weiterhin. `courses`/`ls` sind
auch für ILIAS noch nicht implementiert (`IliasBackend` wirft dort bewusst
`NotSupportedError`, „für ILIAS noch nicht implementiert"). Der ILIAS-Login
(OIDC/Keycloak + TOTP) ist in diesem Branch nach wie vor ein Platzhalter (Exit 1),
`status`/`logout` funktionieren dort, weil der Session-Speicher backend-unabhängig ist.