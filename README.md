# ilias-cli

CLI (später MCP-Server) für **ILIAS** (Hochschule Heilbronn, Uni Mannheim) und **Moodle**
(Hochschule Mannheim). Anforderungen: [ANFORDERUNGEN.md](ANFORDERUNGEN.md), Vertrag:
[INTERFACE.md](INTERFACE.md), Moodle-Details: [MOODLE.md](MOODLE.md).

## Instanzen

`ilias_core` hat ein Backend pro Plattform (`ilias_core.backends`: `IliasBackend`,
`MoodleBackend`) und eine Instanz-Registry in `ilias_core.config`. Eingebaut sind:

| `--instance` | LMS | Login | Befehle |
|---|---|---|---|
| `hhn` (Default) | ILIAS | OIDC/Keycloak (+ TOTP) | login, status, logout |
| `uni-mannheim` | ILIAS | SAML/Shibboleth | login, status, logout |
| `hs-mannheim` | Moodle | Webservice-Token (`moodle_mobile_app`) | login, status, logout, courses, ls |

Jedes Profil lässt sich in `~/.config/ilias-cli/config.toml` (bzw.
`$ILIAS_CLI_CONFIG_DIR/config.toml`) unter `[instances.<key>]` überschreiben oder neu
anlegen (`lms = "ilias" | "moodle"`, `base_url`, bei ILIAS zusätzlich `client_id`, `auth`).
`courses`/`ls` auf einer ILIAS-Instanz enden mit einer sauberen „nicht unterstützt"-Meldung.

```bash
ilias login  --instance hhn                 # ILIAS HHN
ilias login  --instance hs-mannheim         # Moodle: Benutzername + Passwort (verdeckt)
ilias status --instance hs-mannheim --json
ilias courses --instance hs-mannheim
ilias ls PR1 --instance hs-mannheim --depth 2
ilias logout --instance hs-mannheim
```

## Tests

Alle Tests laufen nur gegen localhost-Fake-Server; eine Netzwerk-Sperre lässt jeden
Test scheitern, der einen echten Server erreichen will.

```bash
uv sync
uv run pytest tests/acceptance tests/attempt -q   # ILIAS (Login-Vertrag F1 + A1–A6, Unit-Tests)
uv run pytest tests/moodle -q                     # Moodle (Fake-Moodle)
uv run python tests/acceptance/leak_check.py "<geheimnis>" ~/.config/ilias-cli   # Secret-Leak-Check
```

Exit-Codes: 0 OK · 1 Auth-Fehler/sonstiges · 2 nicht eingeloggt · 3 Session abgelaufen · 4 Netzwerk/Server · 5 Parser-Fehler.
