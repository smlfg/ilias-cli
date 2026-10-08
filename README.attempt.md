# ilias-cli

CLI für ILIAS (Hochschule Heilbronn): Login mit OIDC (Keycloak) + TOTP, Session-Status, Logout.

## Installation

```sh
uv sync
# Browser-Fallback (optionales Extra):
uv sync --extra browser && uv run playwright install chromium
```

## Konfiguration

`~/.config/ilias-cli/config.toml`:

```toml
base_url = "https://ilias.hs-heilbronn.de"
client_id = "iliashhn"
```

Pfad überschreibbar mit der Umgebungsvariable `ILIAS_CLI_CONFIG` (Verzeichnis: `ILIAS_CLI_CONFIG_DIR`).

## Befehle

- `ilias login` — Prompt für Benutzername/Passwort (verdeckt) und TOTP-Code. `--browser` nutzt einen sichtbaren Browser-Login. `--json` für maschinenlesbare Ausgabe.
- `ilias status` — prüft die gespeicherte Session gegen eine geschützte ILIAS-Seite. `--json`.
- `ilias logout` — löscht die gespeicherte Session. `--json`.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| 0 | OK |
| 1 | Allgemeiner Fehler / ungültige Zugangsdaten / Browser nicht verfügbar |
| 2 | Nicht eingeloggt (keine Session gespeichert) |
| 3 | Session abgelaufen (Redirect auf login.php oder Login-Formular in der Seite) |
| 4 | Netzwerk-/Serverfehler |
| 5 | Parser-Fehler (unerwartetes HTML) |

## Sicherheit

- Passwort wird nie gespeichert, geloggt oder ausgegeben; Eingabe nur verdeckt.
- TOTP-Code wird nur interaktiv abgefragt, kein TOTP-Secret wird gespeichert.
- Session-Cookies liegen im OS-Schlüsselbund (keyring), Fallback: `~/.config/ilias-cli/session.json` mit Rechten `0600`.
- Cookies werden nie geloggt und nie in JSON-Ausgaben ausgegeben.
- Session gilt pro Gerät, kein Cookie-Sync.

## Entwicklung

```sh
uv run pytest -q
```
