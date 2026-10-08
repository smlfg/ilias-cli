# ilias-cli

CLI (später MCP-Server) für ILIAS an der Hochschule Heilbronn. Anforderungen: [ANFORDERUNGEN.md](ANFORDERUNGEN.md).

`main` enthält nur den **Vertrag**: Skeleton (`ilias_core`, Kommando `ilias`), [INTERFACE.md](INTERFACE.md) und die modellunabhängige **Akzeptanz-Testsuite** unter `tests/acceptance/` für den Login-Teil (F1 + A1–A6). Die Skeleton-Befehle sind absichtlich nicht implementiert, die Suite ist auf `main` also rot.

Implementierungen verschiedener Modelle liegen auf `attempt/<modell>`-Branches und werden über die gleiche Suite verglichen.

```bash
uv sync
uv run pytest tests/acceptance -q          # Akzeptanztests (nur localhost-Fake-Server, keine echten Requests)
uv run python tests/acceptance/leak_check.py "<geheimnis>" ~/.config/ilias-cli   # Secret-Leak-Check
```

Exit-Codes: 0 OK · 1 Auth-Fehler/sonstiges · 2 nicht eingeloggt · 3 Session abgelaufen · 4 Netzwerk/Server · 5 Parser-Fehler.

## Moodle-Login (Branch `moodle/…`)

Login/Status/Logout laufen über den offiziellen Moodle-Mobile-Webservice
(`POST /login/token.php` → `core_webservice_get_site_info`). Es gibt kein
`--password`-Flag; Benutzername und Passwort werden interaktiv abgefragt, der
Token landet im Keyring (sonst in einer Datei mit Rechten `0600`) und wird nie
ausgegeben.

```bash
uv run ilias login  --instance hs-mannheim [--json]
uv run ilias status --instance hs-mannheim [--json]
uv run ilias logout --instance hs-mannheim [--json]
```

Konfiguration liegt in `$ILIAS_CLI_CONFIG_DIR/config.toml` (sonst
`~/.config/ilias-cli/config.toml`). Vorrang (hoch → niedrig): CLI-Argumente,
`[instances.<key>]` der gewählten Instanz, flache Schlüssel, eingebautes Profil,
Defaults. Das Profil `hs-mannheim` bleibt der Moodle-Default.

```toml
instance = "hs-mannheim"          # wählt das Profil
base_url = "https://moodle.hs-mannheim.de"   # flach, gilt als Default

[instances.hs-mannheim]           # überschreibt flache Werte für diese Instanz
lms = "moodle"
base_url = "http://127.0.0.1:8080"
```

Netzwerk-Sandbox: Der CLI-Subprozess der Tests blockiert jeden Nicht-Loopback-
Zugriff (`tests/moodle/support/sitecustomize.py`) und protokolliert ihn.
