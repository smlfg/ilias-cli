# ILIAS-CLI (Login-Teil)

Kommandozeilen-Tool für den Zugriff auf ILIAS (Hochschule Heilbronn) mit
HHN-Account und 2FA. Dieses Repository enthält den **Login-Teil** der
ILIAS-CLI: `ilias login`, `ilias status`, `ilias logout` inkl. Config,
Session, Fehlerbehandlung und Tests.

Später nutzt ein MCP-Server dieselben Kernfunktionen aus `ilias_core`.

## Installation

```bash
uv sync
# optionaler Browser-Login-Fallback:
uv sync --extra browser
```

## Architektur

```
src/
├── ilias_core/          # KERNBIBLIOTHEK - enthält ALLE Logik
│   ├── config.py        #   Config (~/.config/ilias-cli/config.toml, Defaults HHN)
│   ├── errors.py        #   Exception-Hierarchie -> Exit-Codes
│   ├── models.py        #   LoginResult, SessionStatus, SessionData
│   ├── http.py          #   httpx-Client (User-Agent, Timeouts)
│   ├── auth/
│   │   ├── parser.py    #   Keycloak-Formular-Parser (Login + TOTP)
│   │   ├── flow.py      #   headless OIDC-Login-Flow (httpx)
│   │   └── browser.py   #   Playwright-Fallback (--browser, lazy import)
│   └── session/
│       ├── store.py     #   keyring / Datei(0600) / In-Memory
│       └── manager.py   #   SessionManager + Gültigkeitsprüfung
└── ilias_cli/           # dünne Typer-Hülle (keine Logik)
    ├── main.py          #   typer-App, Entry point `ilias`
    └── commands/        #   login / status / logout
```

**Trennung:** Die Kernfunktionen machen nie selbst Prompts oder prints.
Passwort und TOTP werden als Parameter übergeben. Die CLI ist nur
Prompts, Ausgabe (Tabelle/Text oder JSON) und Exception -> Exit-Code.

## Befehle

```bash
ilias login              # headless (httpx), Passwort+TOTP werden verdeckt abgefragt
ilias login --browser    # Login in sichtbarem Playwright-Browser, Cookies werden übernommen
ilias status             # Session prüfen
ilias logout             # Session löschen
```

Jeder Befehl kennt `--json` für maschinenlesbare Ausgabe (ohne Cookies).

## Exit-Codes

| Code | Bedeutung |
|------|-----------|
| 0    | OK |
| 2    | nicht eingeloggt (keine Session, oder Login fehlgeschlagen) |
| 3    | Session abgelaufen |
| 4    | Netzwerk/Server-Fehler |
| 5    | Parser-Fehler (unerwartetes HTML) |

## Konfiguration

Datei `~/.config/ilias-cli/config.toml` (Pfad über die Environment-Variable
`ILIAS_CLI_CONFIG` überschreibbar, z. B. für Tests):

```toml
base_url = "https://ilias.hs-heilbronn.de"
client_id = "iliashhn"
```

Nichts ist hart kodiert außer diesen HHN-Defaults.

## Sicherheit (A1-A6)

- **A1:** Das Passwort wird nie gespeichert, geloggt, ausgeben oder in
  Exceptions/Reprs gepackt. Die Eingabe erfolgt nur verdeckt per TTY
  (`typer.prompt(..., hide_input=True)`). Es gibt kein `--password`-Flag.
- **A2:** Der TOTP-Code wird interaktiv abgefragt. Es wird kein
  TOTP-Secret gespeichert.
- **A3:** Der Login-Flow baut den normalen Browser-Flow nach
  (`openidconnect.php` -> Keycloak-Login -> TOTP -> Redirects -> ILIAS-
  Session-Cookie). Es wird **kein** Device-Flow verwendet und der Client
  `hhn_common_ilias` nicht für Token-Requests "geliehen".
- **A4:** Session-Cookies liegen im OS-Schlüsselbund (`keyring`) oder in
  einer Datei mit Rechten `0600` (wenn kein Keyring verfügbar ist). Cookies
  werden nie geloggt und nie ausgegeben (auch nicht in `status --json`).
- **A5:** `ilias status` prüft die Session mit einem Request auf eine
  geschützte ILIAS-Seite (`ilias.php?baseClass=ilDashboardGUI`). Redirect
  auf `login.php` (oder Login-Formular im HTML) => Session abgelaufen =>
  klare Meldung + Exit 3. Es wird **kein** automatischer Re-Login versucht.
- **A6:** Die Session ist pro Gerät. Es gibt keinen Cookie-Sync zwischen
  Geräten.

## Tests

```bash
uv run pytest -q
```

Die Tests laufen komplett offline mit `httpx.MockTransport` (keine echten
Netzwerkaufrufe). Realistische HTML-Fixtures liegen unter `tests/fixtures/`.
Der Keyring wird in Tests durch ein In-Memory-Backend ersetzt; der Browser
wird gemockt.

## Entwicklung

```bash
uv run ilias --help
uv run ilias login --help
uv run ilias status --help
```
