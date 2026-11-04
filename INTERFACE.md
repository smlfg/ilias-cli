# INTERFACE.md – Vertrag für Implementierungen

Die Akzeptanztests unter `tests/acceptance/` testen **nur** diese Schnittstelle. Interne
Modulstruktur ist frei, solange die Architektur-Vorgabe aus ANFORDERUNGEN.md §1 gilt
(`ilias_core` = Logik, CLI = dünne Hülle). Die UX-Spec steht in `docs/UX.md`; ihre drei
Sitzungen (Installation+Login, `courses`/`ls`, `download` mit `[j/N]`) sind verbindlich.

## 1. Paket & Kommando
- Python ≥ 3.11, Paketierung mit `uv` (`pyproject.toml`). Nach `uv sync` existiert das Konsolen-Kommando **`ilias`** im venv.
- Paket `ilias_core` enthält Auth, Session, Config, Modelle, Fehler. Rückgabewerte sind strukturierte Daten (Pydantic/Dataclass).
- Akzeptanztests brauchen nur `pytest` (dev-Gruppe) + stdlib. Sie starten `ilias` als **Subprozess** (venv neben `sys.executable` oder `$ILIAS_BIN`).

## 2. Befehle

Alle Befehle nehmen Suchbegriffe **positional** (Name, Kursnummer oder ID), nicht als
Pflicht-Option. `--instance` und `--debug` sind bei jedem Unterbefehl erlaubt; `--json`
ist eine Option **des Unterbefehls** (`ilias status --json`, nicht `ilias --json status`).

| Aufruf | Erfolg | Hinweise |
|---|---|---|
| `ilias login [--instance NAME] [--json] [--browser] [--username NAME]` | Exit 0, Session gespeichert | Fragt nacheinander **Benutzername**, **Passwort** (verdeckt), bei der HHN **TOTP-Code** (verdeckt) ab. `--browser` nur ILIAS. |
| `ilias status [--instance NAME] [--json]` | Exit 0, wenn Session gültig | Wirkt als „wer bin ich?“/whoami: prüft `{base_url}/ilias.php?baseClass=ilDashboardGUI`; zeigt Instanz, LMS und Login-Zustand, nie Cookies. |
| `ilias logout [--instance NAME] [--json]` | Exit 0 (auch ohne Session) | Idempotent. Löscht Session aus Keyring **und** Datei. |
| `ilias courses [--instance NAME] [--json]` | Exit 0, Liste | Eigene Kurse/Gruppen mit ID, Name, Semester. Rein lesend. |
| `ilias ls <kurs> [--depth N] [--instance NAME] [--json]` | Exit 0, Baum | `<kurs>` ist ID, Kursnummer oder Teilstring von Name/Kurzname (positional). Rein lesend. |
| `ilias download <kurs> [pfad] [-o DIR] [--confirm\|--yes] [--dry-run] [--force] [--instance NAME] [--json]` | Exit 0, Dateien lokal | `<kurs>` wie bei `ls`, `pfad` optional relativ zum Kurs oder eine Datei-ref_id. Schreibt **nur lokal**; Server wird nie verändert. |

Weitere Regeln:

- **Kein `--password`/`--totp`-Flag** und keine Credential-Env (A1/A2). Zugangsdaten kommen
  ausschließlich aus der verdeckten interaktiven Eingabe. `ILIAS_CLI_BASE_URL` ist keine
  Credential-Variable.
- **Mehrdeutige Kurse:** Passen mehrere Kurse auf den Suchbegriff, listet das Tool die
  Treffer mit Nummer und endet mit Exit 1 (ohne TTY: Liste + Hinweis). Im TTY darf eine
  nummerierte Auswahl angeboten werden.
- **`download`-Bestätigung:** Im TTY erscheinen vor dem ersten Schreibzugriff Kurs,
  Zielordner und Dateianzahl sowie auf **stderr** `Download verbindlich? [j/N]` (Default
  Nein). Erst nach `j` werden alle Datei-GETs und lokalen Schreibschritte ausgeführt; bei
  `N` endet der Befehl vor dem ersten Schreibzugriff mit Exit 1.
- **Ohne TTY:** `download` ohne `--confirm`/`--yes` bricht vor dem ersten Schreibzugriff ab
  (Exit 1) und nennt den nächsten Schritt (`--confirm` für Agenten). `--dry-run` sendet
  keine Datei-GETs und schreibt nichts. `--confirm`/`--yes` sind **nur** für Agenten.
- **Moodle:** `download` ist derzeit nur für ILIAS-Instanzen implementiert; Moodle endet
  mit Exit 1 und einem Hinweis (`--instance hhn`).
- **`--json`/Pipe:** Mit `--json` steht auf stdout genau ein JSON-Objekt. Ohne `--json`
  liefert ein Nicht-TTY-stdout (Pipe/Agent) ebenfalls JSON; im TTY erscheint lesbarer Text.
  Prompts, Fortschritt und Bestätigungen gehen immer auf stderr, JSON-Ausgaben enthalten
  nie Cookies, Passwörter oder TOTP-Codes.
- **EOF/Strg+C:** Abbruch an einem Prompt (EOF, Strg+C) endet ohne Traceback mit Exit 1
  bzw. 130 und der Meldung „Abgebrochen.“.
- `--version` und jeder `--help`-Aufruf enden mit Exit 0.

### Eingabe ohne TTY
Die Tests starten `ilias login` ohne Controlling-Terminal (`start_new_session=True`) und
schreiben `Benutzername\nPasswort\nTOTP\n` auf stdin. `typer.prompt(..., hide_input=True)`
/ `getpass` lesen dann von stdin – das reicht. Die Reihenfolge Benutzername → Passwort →
TOTP muss eingehalten werden (TOTP darf auch erst nach dem Passwort-POST abgefragt
werden).

## 3. Exit-Codes
| Code | Bedeutung |
|---|---|
| 0 | OK |
| 1 | Login fehlgeschlagen (falsches Passwort/TOTP) oder sonstiger Fehler – **2 ist für Auth-Fehler ebenfalls akzeptiert** |
| 2 | Nicht eingeloggt (keine gespeicherte Session) |
| 3 | Session abgelaufen (Redirect auf `login.php`/Login-Formular). **Kein** automatischer Re-Login |
| 4 | Netzwerk-/Serverfehler (Verbindung fehlgeschlagen, HTTP ≥ 500) |
| 5 | Parser-Fehler (unerwartetes HTML, z. B. kein Keycloak-Formular) |
| 130 | Abbruch per Strg+C (kein Traceback) |

Die Codes 0–5 bleiben unverändert. Ein Abbruch durch `N` oder fehlendes TTY bei
`download` nutzt 1; „nicht eingeloggt“ bleibt 2.

## 4. Konfiguration
- Datei `config.toml` mit `base_url` (z. B. `https://ilias.hs-heilbronn.de`, darf einen Pfad-Präfix haben wie `https://host/ilias`) und `client_id` (z. B. `iliashhn`).
- Ort: `$ILIAS_CLI_CONFIG_DIR/config.toml`, sonst `~/.config/ilias-cli/config.toml` (`~` = `$HOME`).
- **Basis-URL per Env:** `ILIAS_CLI_BASE_URL` überschreibt die `base_url` der aktiven
  Instanz (nach `--instance`/config.toml, vor dem eingebauten Default). Sie ersetzt
  **nur** die URL, nicht `ILIAS_CLI_CONFIG_DIR`, Client-ID oder Session-Pfad. Damit laufen
  UX-Gate und Akzeptanztests gegen einen Fake-Server.
- Weitere Env: `ILIAS_CLI_CONFIG_DIR` (Konfigurationsordner), `ILIAS_CLI_REQUEST_INTERVAL`
  (Sekunden zwischen Requests, Default 1) und `ILIAS_CLI_MAX_REQUESTS` (Crawl-Obergrenze,
  Default 300). Ungültige Zahlen werden ohne Traceback ignoriert bzw. als Fehler gemeldet.
- Dateien, die das Tool schreibt (z. B. Session-Fallback), liegen in `$ILIAS_CLI_CONFIG_DIR` bzw. `~/.config/ilias-cli/`, **nie** im Arbeitsverzeichnis.
- Defaults (HHN), wenn keine Datei existiert: `https://ilias.hs-heilbronn.de`, `iliashhn`.
- Datumsabhängige Befehle (derzeit keine) nutzen `ILIAS_CLI_HEUTE=JJJJ-MM-TT` nur für
  deterministische Tests; die Bedienung im Terminal bleibt „heute/morgen/woche“.

## 5. Session-Speicher (A4)
- Bevorzugt `keyring` (Service `ilias-cli`, Benutzer
  `session:<instance>|<base_url>|<client_id>`; die Tests setzen
  `PYTHON_KEYRING_BACKEND` auf ein Test-Backend und lesen dessen Inhalt).
- Ist kein Keyring nutzbar (`keyring.backends.fail.Keyring`, wirft `NoKeyringError`), Fallback auf eine Datei mit Rechten **0600**.
- **Session-Pfad (Fallback):** `$ILIAS_CLI_CONFIG_DIR/session-<instance>.json`, sonst
  `~/.config/ilias-cli/session-<instance>.json`. Die Datei enthält nur die Cookies als
  JSON, wird mit Modus `0600` geschrieben und nie im Arbeitsverzeichnis abgelegt.
- Gespeichert werden nur ILIAS-Cookies (z. B. `PHPSESSID`, `ilClientId`), keine Keycloak-Cookies (`KEYCLOAK_IDENTITY`, `AUTH_SESSION_ID`), nie Passwort oder TOTP.

## 6. HTTP-Flow (A3), wie ihn der Fake-Server nachbildet
1. `GET {base_url}/openidconnect.php` → `302` auf `{keycloak}/realms/hhn/protocol/openid-connect/auth?client_id=hhn_common_ilias&redirect_uri=…&state=…`
2. Keycloak antwortet `200` mit `<form id="kc-form-login" action="…/login-actions/authenticate?session_code=…&amp;execution=…&amp;client_id=…&amp;tab_id=…">` (absolute URL, HTML-Entities!), Felder `username`, `password`, hidden `credentialId` und ggf. weitere hidden inputs (alle mitsenden). Cookie `AUTH_SESSION_ID` muss zurückgeschickt werden.
3. `POST` username/password → `200` TOTP-Formular `<form id="kc-otp-login-form" action="…">` mit Feld `otp` (+ hidden inputs) **oder** `200` Login-Formular mit Fehler (`#input-error`, `.kc-feedback-text`).
4. `POST otp` → `302` auf `{base_url}/openidconnect.php?state=…&code=…` **oder** `200` TOTP-Formular mit Fehler (`#input-error-otp-code`).
5. ILIAS setzt neues `PHPSESSID` (+ `ilClientId`) und leitet aufs Dashboard weiter.
6. Abgelaufen: `GET ilias.php?baseClass=ilDashboardGUI` → `302 login.php?…&cmd=force_login`.
- Eigener User-Agent `ilias-cli/<version>`.
- Keycloak liegt in den Tests auf einem anderen Host (`localhost`) als ILIAS (`127.0.0.1`), wie in echt (`login.hs-heilbronn.de` vs. `ilias.hs-heilbronn.de`).

## 7. Netzwerk-Sandbox
Der CLI-Subprozess läuft mit `support/sitecustomize.py` (über `PYTHONPATH`): Verbindungen/DNS zu allem außer Loopback werden blockiert und protokolliert, zusätzlich zeigen `HTTP(S)_PROXY` auf einen toten Port (`NO_PROXY=127.0.0.1,localhost`). Jeder blockierte Versuch lässt den Test fehlschlagen. Implementierungen dürfen also nie auf echte Server zurückfallen, z. B. weil sie `ILIAS_CLI_CONFIG_DIR` ignorieren.

## 7a. Erweiterungen (Branch `feature/saml-uni-mannheim`)
- **Verifizierter Login:** `login` meldet Exit 0 und speichert nur, wenn (1) die Redirect-Kette nach dem letzten IdP-Schritt bei ILIAS endet, (2) das ILIAS-Session-Cookie neu/geändert ist und (3) `ilias.php?baseClass=ilDashboardGUI` nicht auf `login.php` umleitet und ein Login-Merkmal (Abmelde-Link `logout.php`) zeigt. Sonst: Auth-Fehler (1) bzw. Parser-Fehler (5). `status` prüft dasselbe Dashboard (Login-Seite/Redirect ⇒ 3, ohne Merkmal ⇒ 5).
- **Instanzen:** `--instance <name>` an allen Befehlen bzw. `instance = "..."` in `config.toml`. Eingebaut: `hhn` (Default, `oidc-keycloak`) und `uni-mannheim` (`https://ilias.uni-mannheim.de`, `ILIAS`, `saml-shibboleth`). Overrides unter `[instances.<name>]`; Schlüssel auf oberster Ebene gelten für die Instanz aus `instance`. Sessions pro Instanz.
- **`saml-shibboleth`:** fragt Benutzername und Passwort ab, kein TOTP. Falsches Passwort ⇒ 1.
- **`--debug`:** loggt auf stderr nur URLs (Query-Werte geschwärzt außer `baseClass`, `cmd`, `cmdClass`, `execution`, `client_id`, `lang`), Statuscodes, Formular-IDs und Feldnamen.

## 8. Secret-Leak-Check
`tests/acceptance/leak_check.py <secret> <pfade…>` sucht ein Geheimnis (roh, URL- und Base64-kodiert) in Dateibäumen. Die Akzeptanztests prüfen damit stdout/stderr aller Aufrufe (inkl. Tracebacks) und alle geschriebenen Dateien inkl. Keyring auf das Test-Passwort.
