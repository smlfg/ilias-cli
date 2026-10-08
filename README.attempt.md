# ilias-cli (Phase 1: Login)

Kommandozeilen-Tool für ILIAS. Phase 1 umfasst ausschließlich **Login, Status
und Logout** inklusive 2FA. Kurse, Fristen, Downloads und der MCP-Server folgen
später auf derselben Kernbibliothek.

## Architektur

- `ilias_core` – gesamte Logik: `config`, `auth` (OIDC/Keycloak-Flow + Parser),
  `session` (Cookie-Speicher), `models`, `errors`, `browser` (optional), `client`.
  Kernfunktionen machen **keine** Prompts und **keine** Ausgabe. Passwort und
  TOTP werden als Parameter bzw. Callback übergeben.
- `ilias_cli` – dünne Hülle: Prompts, Ausgabe (Text/JSON), Übersetzung von
  `IliasError` in Exit-Codes.

## Installation

```bash
uv sync                 # installiert das Projekt + Dev-Abhängigkeiten
uv run ilias --help
```

Für den Browser-Fallback zusätzlich:

```bash
uv sync --extra browser
uv run playwright install chromium
```

## Befehle

```bash
uv run ilias login                 # OIDC-Login (Benutzername, verdecktes Passwort, TOTP)
uv run ilias login --json          # maschinenlesbare Ausgabe
uv run ilias login --browser       # sichtbarer Browser, Nutzer loggt sich selbst ein
uv run ilias status                # prüft die gespeicherte Session
uv run ilias status --json
uv run ilias logout                # löscht die gespeicherte Session
uv run ilias logout --json
```

### Exit-Codes

| Code | Bedeutung |
|-----:|-----------|
| 0 | OK |
| 1 | Allgemeiner Fehler (z. B. falsches Passwort/TOTP, fehlendes Playwright, Konfigurationsfehler) |
| 2 | Nicht eingeloggt (keine gespeicherte Session) |
| 3 | Session abgelaufen |
| 4 | Netzwerk- oder Serverfehler |
| 5 | Parser-Fehler (unerwartetes HTML) |

`status` liefert bei fehlender Session Exit-Code 2, bei abgelaufener Session
Exit-Code 3 und **keinen** automatischen Re-Login.

## Konfiguration

Es gilt `~/.config/ilias-cli/config.toml`:

```toml
base_url = "https://ilias.hs-heilbronn.de"  # HHN-Default
client_id = "iliashhn"                       # HHN-Default
```

Der Ordner lässt sich per Umgebungsvariable `ILIAS_CLI_CONFIG_DIR` (z. B. für
Tests) überschreiben. Basis-URL und Client-ID sind nicht hart kodiert.

## Sicherheit (A1–A6)

- **A1** Das Passwort wird nie gespeichert, geloggt, ausgegeben oder in
  Exceptions/Reprs gepackt. Eingabe nur verdeckt (`typer.prompt(hide_input=True)`).
  Es gibt kein `--password`-Flag.
- **A2** Der TOTP-Code wird interaktiv abgefragt. Ein TOTP-Secret wird nie
  gespeichert.
- **A3** Headless-Login per `httpx`: `openidconnect.php` → Keycloak-Formular
  (action + alle hidden inputs) → `POST username/password` → ggf. TOTP →
  Redirects zurück zu ILIAS → Session-Cookies. Fallback `--browser` (Playwright,
  optionales Extra, lazy importiert). Fehlerfälle (falsches Passwort/TOTP,
  unerwartetes HTML) werden klar unterschieden.
- **A4** Cookies liegen im OS-Schlüsselbund (`keyring`). Ohne Schlüsselbund
  Fallback in `~/.config/ilias-cli/session.json` mit Rechten `0600`. Cookies
  werden nie geloggt oder ausgegeben – auch nicht bei `status --json`.
- **A5** `status` prüft eine geschützte ILIAS-Seite
  (`ilias.php?baseClass=ilDashboardGUI`). Redirect auf `login.php` oder ein
  Login-Formular ⇒ Exit 3. Kein automatischer Re-Login.
- **A6** Session pro Gerät, kein Cookie-Sync.

Der User-Agent ist `ilias-cli/<version>`, die Timeouts sind begrenzt.

## Tests

```bash
uv run pytest -q
```

Alle Tests laufen ohne echte Netzwerkzugriffe (`respx` bzw. `httpx.MockTransport`)
und mit realistischen HTML-Fixtures unter `tests/fixtures/`. Der Schlüsselbund
wird in Tests durch ein In-Memory-Backend ersetzt.

## Lizenz

MIT.
