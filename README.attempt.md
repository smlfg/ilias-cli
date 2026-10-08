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
uv run ilias login                 # HHN: OIDC-Login (Benutzername, verdecktes Passwort, TOTP)
uv run ilias login --instance uni-mannheim   # SAML/Shibboleth (Uni-ID, Passwort, kein TOTP)
uv run ilias login --json          # maschinenlesbare Ausgabe
uv run ilias login --browser       # sichtbarer Browser, Nutzer loggt sich selbst ein
uv run ilias status                # prüft die gespeicherte Session
uv run ilias status --json
uv run ilias logout                # löscht die gespeicherte Session
uv run ilias logout --json
```

Alle Befehle kennen `--instance <name>` und `--debug` (sicheres Log auf stderr:
URLs ohne Query-Werte außer Routing-Parametern, Statuscodes, Formularfeld-Namen;
nie Werte, Passwörter oder Cookies). Anleitung für den ersten echten Test:
[REAL_TEST.md](REAL_TEST.md).

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

Eingebaute Instanz-Profile:

| Instanz | Basis-URL | client_id | auth |
|---|---|---|---|
| `hhn` (Default) | `https://ilias.hs-heilbronn.de` | `iliashhn` | `oidc-keycloak` |
| `uni-mannheim` | `https://ilias.uni-mannheim.de` | `ILIAS` | `saml-shibboleth` |

```toml
instance = "uni-mannheim"     # aktive Instanz (sonst hhn); --instance hat Vorrang
base_url = "https://..."      # überschreibt Werte der aktiven Instanz
client_id = "..."
auth = "saml-shibboleth"      # oder "oidc-keycloak"

[instances.meine-uni]         # Overrides pro Instanz oder eigene Instanz
base_url = "https://ilias.example.org"
client_id = "ILIAS"
auth = "saml-shibboleth"
```

Schlüssel auf oberster Ebene gelten nur für die Instanz aus `instance`.
Der Ordner lässt sich per Umgebungsvariable `ILIAS_CLI_CONFIG_DIR` (z. B. für
Tests) überschreiben. Sessions werden pro Instanz gespeichert.

## Sicherheit (A1–A6)

- **A1** Das Passwort wird nie gespeichert, geloggt, ausgegeben oder in
  Exceptions/Reprs gepackt. Eingabe nur verdeckt (`typer.prompt(hide_input=True)`).
  Es gibt kein `--password`-Flag.
- **A2** Der TOTP-Code wird interaktiv abgefragt. Ein TOTP-Secret wird nie
  gespeichert.
- **A3** Headless-Login per `httpx`, Adapter je nach `auth`:
  - `oidc-keycloak`: `openidconnect.php` → Keycloak-Formular (action + alle
    hidden inputs) → `POST username/password` → ggf. TOTP → Redirects zu ILIAS.
  - `saml-shibboleth`: `saml.php` → IdP `form#login-form` (`csrf_token`) →
    `POST j_username/j_password/_eventId_proceed` → ggf. Attributfreigabe
    (vorausgewählte Option) → Auto-Submit-Formular mit `SAMLResponse` → ILIAS.

  Erfolg wird erst gemeldet (und gespeichert), wenn die Redirect-Kette bei ILIAS
  endet, das Session-Cookie neu ist und das Dashboard nicht auf `login.php`
  umleitet und einen Abmelde-Link zeigt. Fallback `--browser` (Playwright,
  sichtbar, optionales Extra), danach dieselbe Dashboard-Prüfung.
- **A4** Cookies liegen im OS-Schlüsselbund (`keyring`). Ohne Schlüsselbund
  Fallback in `~/.config/ilias-cli/session-<instanz>.json` mit Rechten `0600`.
  Nur ILIAS-Cookies, keine IdP-Cookies (Keycloak, `shib_idp_session`, `JSESSIONID`).
  Cookies werden nie geloggt oder ausgegeben – auch nicht bei `status --json`.
- **A5** `status` prüft `ilias.php?baseClass=ilDashboardGUI`. Redirect auf
  `login.php`, Login-Seite oder IdP ⇒ Exit 3; Seite ohne Login-Merkmal ⇒ Exit 5.
  Kein automatischer Re-Login.
- **A6** Session pro Gerät, kein Cookie-Sync.

Der User-Agent ist `ilias-cli/<version>`, die Timeouts sind begrenzt.

## Tests

```bash
uv run pytest -q
```

Alle Tests laufen ohne echte Netzwerkzugriffe: Unit-Tests unter `tests/attempt`
mit `respx` und einer Loopback-Sperre, Subprozess-Tests unter `tests/acceptance`
gegen lokale Fake-Server (Keycloak bzw. Shibboleth-IdP + ILIAS) mit Netzwerk-Sandbox.
Die SAML-Fakes nutzen die echten, anonym erfassten Seiten unter
`tests/fixtures/uni-mannheim/`.

## Lizenz

MIT.
