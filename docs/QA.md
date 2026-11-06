# Pflicht-QA (Schritt 6)

Datum: 2026-11-06  
Getesteter Stand: Commit `bf8aa6e` (Branch `main`), Version `0.1.0`;  
Nachprüfung der zwei FAILs auf `d240b8a`, Version `0.1.0`  
Installation: orchestrator-seitig mit `pipx install git+https://github.com/smlfg/ilias-cli`
in `scratch/pipx`; alle Aufrufe über `PATH=$PWD/scratch/pipx/bin:$PATH`.
Synthetische Sitzungen gegen `tests/harness/fake_server.py` mit den Routen aus
`docs/UX.md`; Live-Zugriffe ausschließlich lesend (GET) auf öffentliche Seiten
bzw. mit einer bewusst ungültigen Session auf das Dashboard.

## Ergebnis

**44 von 44 Prüfungen OK, 0 FAIL** (nach Nachprüfung).

Die beiden ursprünglichen FAILs sind behoben:

1. **Automatisches JSON bei Pipe/Nicht-TTY-stdout** – Fix `e7e0473`.
2. **Usage-Fehler mit `--json` liefern JSON** – Fix `d240b8a`.

Details in `scratch/QA-FAILS.md`. Beide Befehlsgruppen wurden nach den Fixes
live erneut ausgeführt (Fake-Server, Installation aus dem Arbeitsstand).

## Prüfungen

| # | Prüfung | Befehl (gekürzt) | Erwartet | Ergebnis | Beleg |
|---|---|---|---|---|---|
| 1 | Frische pipx-Installation | `cat scratch/qa/pipx-install.log`; `ilias --version` | Paket installiert, `ilias` im PATH | OK | `installed package ilias-cli 0.1.0`; `0.1.0` (Exit 0) |
| 2 | `--version` | `ilias --version` | Exit 0, Version | OK | `0.1.0`, Exit 0 |
| 3 | Root-`--help` | `ilias --help` | Exit 0, verständlich | OK | Exit 0, Befehle/Flags erklärt |
| 4 | Hilfe aller Unterbefehle | `ilias <sub> --help` für login/status/logout/courses/ls/download | je Exit 0 | OK | alle Exit 0 |
| 5 | README-Login im Pseudo-TTY | `script -qc "ilias login"` mit Benutzer/Passwort/TOTP | Prompts, verdeckt, Exit 0 | OK | `Benutzername:` / `Passwort:` / `TOTP-Code:`, Passwort+TOTP nicht im Log, Exit 0 |
| 6 | Login-EOF | Passwort-Prompt + Strg+D | Exit 1, „Abgebrochen.“, kein Traceback | OK | Exit 1, `Fehler: Abgebrochen.` |
| 7 | Login-Strg+C live | `ilias login` (HHN) + Strg+C am Benutzername-Prompt | Exit 130, kein Traceback | OK | Exit 130, `Fehler: Abgebrochen.` |
| 8 | Login ohne TTY | `printf 'user\npass\ntotp\n' \| ilias login` | Exit 0, Session gespeichert | OK | Exit 0, `Login erfolgreich und geprüft` |
| 9 | Session-Rechte | `stat -c %a session-hhn.json` | `600` | OK | `600` |
| 10 | `courses` im TTY | `script -qc "ilias courses"` | lesbare Tabelle, plausible Daten | OK | `900101`, `Beispielkurs Programmierung (WiSe 2026/27)`, `WiSe 2026/27` |
| 11 | `ls` voller Name | `ilias ls "Beispielkurs Programmierung"` | Kursinhalt als Baum | OK | `Inhalt`, `Blatt 10`, `Übung 3 --> Lösung`, Exit 0 |
| 12 | `ls` Teilstring/Groß-Klein | `ilias ls Beispielkurs`, `... "beispielkurs programmierung"`, `... PROGRAMMIERUNG` | je Treffer | OK | je Exit 0, gleicher Kurs |
| 13 | `ls` per ID | `ilias ls 900101` | Treffer | OK | Exit 0, gleicher Kurs |
| 14 | `ls` mit Umlaut | `ilias ls "Programmierung für Anfänger"`, `... "für"` (eigener Fake-Kurs) | exakter Umlaut-Treffer | OK | je Exit 0; Transliteration `Uebungskurs` trifft bewusst nicht (nicht spezifiziert) |
| 15 | Mehrdeutig ohne TTY | `ilias ls Übungskurs` (zwei Kurse) | Liste + Exit 1 | OK | `Mehrere Kurse passen ... 910001 ... 910002`, Exit 1 |
| 16 | Mehrdeutig im TTY | `script -qc "ilias ls Übungskurs"`, Eingabe `2` | nummerierte Auswahl, gewählter Kurs | OK | Liste 1/2, `Übungskurs Datenbanken ...`, Exit 0 |
| 17 | Leeres Ergebnis | `ilias ls gibtsnicht` | Exit 1, nächster Schritt | OK | `Kein Kurs passt ...`, Hinweis auf `ilias courses`, Exit 1 |
| 18 | Download bestätigt (`j`) | `ilias download "Beispielkurs Programmierung" --force`, `j` | erst nach `j` schreiben | OK | Plan + `[j/N]`, danach `Blatt 10.pdf` (285 B) + Manifest, Exit 0 |
| 19 | Download abgelehnt (`N`) | gleicher Befehl, `N` | Exit 0, nichts geschrieben | OK | `Abgebrochen. Es wurde nichts geschrieben.`, Zielordner leer |
| 20 | Download ohne TTY | `ilias download ... </dev/null` | Abbruch vor Schreibzugriff, Exit 1 | OK | `keine Bestätigung ohne Terminal`, Hinweis `--confirm`, keine Dateien |
| 21 | Download-EOF | `[j/N]` + Strg+D | Exit 1, kein Traceback, nichts geschrieben | OK | `Fehler: Abgebrochen.`, keine Dateien |
| 22 | Download `--dry-run` | `ilias download 900101 "Blatt 10" -n` | nur Plan, keine Datei-GETs/Schreibzugriffe | OK | `Geplant: 1 Datei(en)`, Zielordner leer |
| 23 | Download inkrementell | zweiter Lauf ohne `--force` | vorhandene Datei überspringen | OK | `Dateien: 1 (neu 0, aktuell 1)`, `1 übersprungen` |
| 24 | Download Pfadfilter | `ilias download 900101 "Blatt 10" -n` | genau die Datei | OK | `Geplant: 1 Datei(en)` |
| 25 | Download falscher Pfad | `ilias download 900101 gibtsnicht -n` | Exit 1, nächster Schritt | OK | `Keine Datei ... passt`, Hinweis auf `ilias ls`, Exit 1 |
| 26 | `--json` lesend | `ilias courses --json` | genau ein valides JSON-Objekt | OK | `python3 -m json.tool` OK, Kurs 900101 |
| 27 | `--json` Download | `ilias download 900101 --confirm --json` | valides JSON, keine Secrets | OK | JSON parsebar, `downloaded`/`items` |
| 28 | `--json` Fehler | `ilias courses --json` ohne Session | valides JSON, Exit 2 | OK | `{"ok": false, ... "exit_code": 2}`, Exit 2 |
| 29 | JSON bei Pipe ohne Flag | `ilias courses \| cat`, `ilias ls ... \| cat`, `ilias status \| cat`, `ilias download ... --confirm \| cat` | genau ein JSON-Objekt | OK (nach Fix e7e0473) | vier Aufrufe Exit 0; stdout je valides JSON (`json.tool` OK), z. B. Kurs 900101 und Download `ok: true` |
| 30 | Usage-Fehler mit `--json` | `ilias ls --json`; `ilias ls 900101 --depth 0 --json` | JSON-Objekt, kein Traceback | OK (nach Fix d240b8a) | Exit 2; stdout je `{"ok": false, ... "error": {"code": "usage_error"} ...}`, `json.tool` OK, kein Traceback |
| 31 | Falsche Basis-URL (Netz) | `ILIAS_CLI_BASE_URL=http://127.0.0.1:9 ilias courses` | Exit 4, nächster Schritt | OK | `Verbindung fehlgeschlagen`, Hinweis VPN/Erreichbarkeit, Exit 4 |
| 32 | Ungültige Basis-URL | `ILIAS_CLI_BASE_URL=ftp://kaputt ilias courses` | Exit 1, kein Traceback | OK | `keine gültige http(s)-URL`, Hinweis, Exit 1 |
| 33 | Status ohne Session | `ilias status` (leeres Config-Dir) | Exit 2, Hinweis `login` | OK | `Nicht eingeloggt ... ilias login`, Exit 2 |
| 34 | Kurse ohne Session | `ilias courses` (leeres Config-Dir) | Exit 2, Hinweis `login` | OK | `Keine gespeicherte Session ...`, Exit 2 |
| 35 | Logout idempotent | `ilias logout` ohne Session, danach `status` | Exit 0; Status Exit 2 | OK | `Keine gespeicherte Session vorhanden.` Exit 0; Status Exit 2 |
| 36 | Moodle-Download | `ilias download PR1 --instance hs-mannheim --confirm` | Exit 1, Hinweis ILIAS | OK | `noch nicht implementiert`, `--instance hhn`, Exit 1 |
| 37 | `--browser` auf Moodle | `ilias login --instance hs-mannheim --browser` | Exit 1, Hinweis | OK | `nur für ILIAS-Instanzen`, Exit 1 |
| 38 | Live HHN (öffentlich) | `GET https://ilias.hs-heilbronn.de/openidconnect.php` | Keycloak-Formular wie in UX.md | OK | 200, Formular `kc-form-login`, Felder `username/password/credentialId/login` |
| 39 | Live Moodle (öffentlich) | `GET https://moodle.hs-mannheim.de/login/index.php` | Moodle-Loginformular | OK | 200, `form#login`, Felder `username/password/logintoken/anchor` |
| 40 | Live Status HHN (nur GET) | ungültige Session, `ilias status` | Exit 3, erneuter Login | OK | `Session abgelaufen. Bitte erneut ilias login ausführen.`, Exit 3 |
| 41 | Live Kurse HHN (nur GET) | ungültige Session, `ilias courses` | Exit 3, kein Auto-Re-Login | OK | `Session abgelaufen (Weiterleitung/Anmeldeseite)`, Exit 3 |
| 42 | Live Status Uni Mannheim (nur GET) | ungültige Session, `ilias status --instance uni-mannheim` | Exit 3 | OK | `Session abgelaufen ...`, Exit 3 |
| 43 | Testsuite | `scratch/venv/bin/pytest -q` | grün, keine Regression | OK | `356 passed, 21 xfailed, 86 xpassed` in 277 s |
| 44 | UX-Spec-Gate unverändert | `python3 tests/harness/ux_check.py . --spec-only` | PASS, Gate nicht aufgeweicht | OK | UX01/UX06/UX07 PASS, Exit 0 |

## Grenzen der Live-Prüfung

- Ein echtes Konto durfte nicht verwendet werden. Deshalb wurden `courses`, `ls`
  und `download` nicht mit echten Nutzerdaten live ausgeführt. Die lesenden
  Live-Pfade wurden mit einer bewusst ungültigen Session bis zum erwarteten
  Exit 3 geprüft; die vollständigen Daten- und Bestätigungssitzungen liefen
  gegen den Fake-Server aus `docs/UX.md`.
- `ilias.uni-mannheim.de/login.php` leitete beim öffentlichen GET ohne
  Cookie-Jar auf eine IdP-Seite „Veraltete Anfrage“ (HTTP 500) um. Das ist ein
  Zustand der öffentlichen IdP-Antwort, kein Befund am Tool; mit ungültiger
  Session liefert `status --instance uni-mannheim` sauber Exit 3.
- Moodle-Livezugriffe unterblieben, weil der Mobile-Webservice auch für
  Lesezugriffe POST verwendet; ohne Token war kein regelkonformer Live-Aufruf
  möglich.

## Nebenbefunde (keine FAILs)

- `README.md` nennt „326 Tests grün“; aktuell sind es `356 passed` (plus
  xfail/xpass). Reine Dokumentationsabweichung.
- Die menschliche `ls`-Ausgabe zeigt bei leerem Kurznamen `()`, z. B.
  `Beispielkurs Programmierung (WiSe 2026/27) ()`. Kosmetisch; JSON und
  Auswahl funktionieren.
- Eine deutsche Tippvariante mit `ue` statt `ü` (`Uebungskurs`) wird nicht auf
  `Übungskurs` abgebildet. INTERFACE.md fordert nur case-insensitiven
  Teilstring, keine Transliteration; deshalb kein FAIL.
