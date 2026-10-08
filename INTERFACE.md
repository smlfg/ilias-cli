# INTERFACE.md – Vertrag für Implementierungen (Login-Teil, F1 + A1–A6)

Die Akzeptanztests unter `tests/acceptance/` testen **nur** diese Schnittstelle. Interne Modulstruktur ist frei, solange die Architektur-Vorgabe aus ANFORDERUNGEN.md §1 gilt (`ilias_core` = Logik, CLI = dünne Hülle).

## 1. Paket & Kommando
- Python ≥ 3.11, Paketierung mit `uv` (`pyproject.toml`). Nach `uv sync` existiert das Konsolen-Kommando **`ilias`** im venv.
- Paket `ilias_core` enthält Auth, Session, Config, Modelle, Fehler. Rückgabewerte sind strukturierte Daten (Pydantic/Dataclass).
- Akzeptanztests brauchen nur `pytest` (dev-Gruppe) + stdlib. Sie starten `ilias` als **Subprozess** (venv neben `sys.executable` oder `$ILIAS_BIN`).

## 2. Befehle
| Aufruf | Erfolg | Hinweise |
|---|---|---|
| `ilias login [--json]` | Exit 0, Session gespeichert | Fragt nacheinander **Benutzername**, **Passwort** (verdeckt), **TOTP-Code** ab. |
| `ilias status [--json]` | Exit 0, wenn Session gültig | Prüft mit einem Request auf `{base_url}/ilias.php?baseClass=ilDashboardGUI`. |
| `ilias logout [--json]` | Exit 0 (auch ohne Session) | Löscht Session aus Keyring **und** Datei. |

- `--json` ist eine Option **des Unterbefehls** (`ilias status --json`, nicht `ilias --json status`).
- Mit `--json` steht auf stdout genau ein JSON-Objekt. Für `status`/`logout` wird das strikt geprüft; bei `login` ist Prompt-Text vor dem JSON toleriert (besser: Prompts auf stderr). JSON-Ausgaben enthalten nie Cookies.
- Kein `--password`-Flag (A1).

### Eingabe ohne TTY
Die Tests starten `ilias` ohne Controlling-Terminal (`start_new_session=True`) und schreiben `Benutzername\nPasswort\nTOTP\n` auf stdin. `typer.prompt(..., hide_input=True)` / `getpass` lesen dann von stdin – das reicht. Die Reihenfolge Benutzername → Passwort → TOTP muss eingehalten werden (TOTP darf auch erst nach dem Passwort-POST abgefragt werden).

## 3. Exit-Codes
| Code | Bedeutung |
|---|---|
| 0 | OK |
| 1 | Login fehlgeschlagen (falsches Passwort/TOTP) oder sonstiger Fehler – **2 ist für Auth-Fehler ebenfalls akzeptiert** |
| 2 | Nicht eingeloggt (keine gespeicherte Session) |
| 3 | Session abgelaufen (Redirect auf `login.php`/Login-Formular). **Kein** automatischer Re-Login |
| 4 | Netzwerk-/Serverfehler (Verbindung fehlgeschlagen, HTTP ≥ 500) |
| 5 | Parser-Fehler (unerwartetes HTML, z. B. kein Keycloak-Formular) |

## 4. Konfiguration
- Datei `config.toml` mit `base_url` (z. B. `https://ilias.hs-heilbronn.de`, darf einen Pfad-Präfix haben wie `https://host/ilias`) und `client_id` (z. B. `iliashhn`).
- Ort: `$ILIAS_CLI_CONFIG_DIR/config.toml`, sonst `~/.config/ilias-cli/config.toml` (`~` = `$HOME`).
- Dateien, die das Tool schreibt (z. B. Session-Fallback), liegen in `$ILIAS_CLI_CONFIG_DIR` bzw. `~/.config/ilias-cli/`, **nie** im Arbeitsverzeichnis.
- Defaults (HHN), wenn keine Datei existiert: `https://ilias.hs-heilbronn.de`, `iliashhn`.

## 5. Session-Speicher (A4)
- Bevorzugt `keyring` (die Tests setzen `PYTHON_KEYRING_BACKEND` auf ein Test-Backend und lesen dessen Inhalt).
- Ist kein Keyring nutzbar (`keyring.backends.fail.Keyring`, wirft `NoKeyringError`), Fallback auf eine Datei mit Rechten **0600**.
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

## 8. Secret-Leak-Check
`tests/acceptance/leak_check.py <secret> <pfade…>` sucht ein Geheimnis (roh, URL- und Base64-kodiert) in Dateibäumen. Die Akzeptanztests prüfen damit stdout/stderr aller Aufrufe (inkl. Tracebacks) und alle geschriebenen Dateien inkl. Keyring auf das Test-Passwort.
