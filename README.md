# ilias-cli

> **Status: Beta (0.x).** Getestet mit Fixtures und Mocks (326 Tests grün). Ein Live-Test an der
> HHN steht noch aus; Befehle und Ausgaben können sich vor 1.0 ändern.
>
> Installation: `uv tool install ilias-cli` oder `pipx install ilias-cli`, danach `ilias --help`.

CLI (später MCP-Server) für **ILIAS** (Hochschule Heilbronn, Uni Mannheim) und **Moodle**
(Hochschule Mannheim). Anforderungen: [ANFORDERUNGEN.md](ANFORDERUNGEN.md), Vertrag:
[INTERFACE.md](INTERFACE.md), UX-Spec: [docs/UX.md](docs/UX.md), Moodle-Details:
[MOODLE.md](MOODLE.md).

## Schnellstart

```bash
pipx install git+https://github.com/smlfg/ilias-cli
ilias login
ilias courses
ilias ls "Beispielkurs Programmierung"
ilias download "Beispielkurs Programmierung" --force
```

`ilias login` fragt Benutzername und Passwort **verdeckt** ab, bei der HHN zusätzlich den
TOTP-Code. `ls` nimmt den Kursnamen (oder Kursnummer/ID) positional. `download` zeigt
Kurs, Zielordner und Dateianzahl und fragt im Terminal `Download verbindlich? [j/N]`
(Default Nein); erst nach `j` wird lokal geschrieben.

## Instanzen

`ilias_core` hat ein Backend pro Plattform (`ilias_core.backends`: `IliasBackend`,
`MoodleBackend`) und eine Instanz-Registry in `ilias_core.config`. Eingebaut sind:

| `--instance` | LMS | Login | Befehle |
|---|---|---|---|
| `hhn` (Default) | ILIAS | OIDC/Keycloak (+ TOTP) | login, status, logout, courses, ls, **download** |
| `uni-mannheim` | ILIAS | SAML/Shibboleth | login, status, logout, courses, ls, download (ungetestet) |
| `hs-mannheim` | Moodle | Webservice-Token (`moodle_mobile_app`) | login, status, logout, courses, ls |

Jedes Profil lässt sich in `~/.config/ilias-cli/config.toml` (bzw.
`$ILIAS_CLI_CONFIG_DIR/config.toml`) unter `[instances.<key>]` überschreiben oder neu
anlegen (`lms = "ilias" | "moodle"`, `base_url`, bei ILIAS zusätzlich `client_id`, `auth`).
`download` ist derzeit nur auf ILIAS-Instanzen verfügbar (Moodle: nicht unterstützt).

```bash
ilias login  --instance hhn                 # ILIAS HHN
ilias login  --instance hs-mannheim         # Moodle: Benutzername + Passwort (verdeckt)
ilias status --instance hs-mannheim --json
ilias courses --instance hs-mannheim
ilias ls PR1 --instance hs-mannheim --depth 2
ilias logout --instance hs-mannheim
```

### Download (F5, nur ILIAS)

```bash
ilias download 900101 -o ~/Studium                    # ganzer Kurs -> ~/Studium/<Kursname>/<Ordner>/…
ilias download "KI-Programmierung" "Übungsblätter"    # nur ein Ordner (Pfad relativ zum Kurs)
ilias download 900101 900311                          # eine Datei per ref_id (aus `ilias ls --json`)
ilias download 900101 -n                              # --dry-run: nur anzeigen
ilias download 900101 --confirm                       # Agent: ohne [j/N] schreiben
```

- Im TTY erscheinen Kurs, Zielordner und Dateianzahl sowie `Download verbindlich? [j/N]`
  auf stderr; Default ist Nein. Erst nach `j` laufen alle Datei-GETs und lokalen
  Schreibschritte. `--confirm`/`--yes` ist nur für Agenten; ohne TTY und ohne dieses Flag
  bricht `download` vor dem ersten Schreibzugriff ab.
- Zweiter Lauf lädt nur neue oder in ILIAS geänderte Dateien (Manifest `.ilias-download.json`
  im Kursordner). Von Hand abgelegte Dateien mit gleichem Namen werden nicht überschrieben;
  `--force` lädt trotzdem neu.
- Offline-Objekte werden übersprungen. Einzelne verweigerte Dateien stehen als `failed` in der
  Ausgabe, der Rest wird geladen, Exit-Code dann 1. Session abgelaufen -> Exit 3, Server -> Exit 4.
- `--json`: `{ok, course, target_dir, summary{downloaded,skipped,planned,failed}, items[{ref_id,name,path,status,size,error_code,message}]}`.
- Abschnitte der Kursseite („Inhalt“, Objektblöcke) werden nicht zu Ordnern, nur ILIAS-Ordner/Gruppen.

### Ausgabe und Umgebung

- Im Terminal lesbarer Text; mit `--json` oder wenn stdout kein TTY ist (Pipe/Agent) genau
  ein JSON-Objekt auf stdout. Prompts und Bestätigungen gehen auf stderr.
- `ILIAS_CLI_BASE_URL` überschreibt die Basis-URL der aktiven Instanz (z. B. für
  Fake-Server); `ILIAS_CLI_CONFIG_DIR` bleibt der Konfigurationsordner.
- Session: Keyring oder Datei `session-<instance>.json` mit Rechten `0600` unter
  `~/.config/ilias-cli/` (bzw. `$ILIAS_CLI_CONFIG_DIR`). Keine Cookies in der Ausgabe.

## Tests

Alle Tests laufen nur gegen localhost-Fake-Server; eine Netzwerk-Sperre lässt jeden
Test scheitern, der einen echten Server erreichen will.

```bash
uv sync
uv run pytest tests/acceptance tests/attempt -q   # ILIAS (Login-Vertrag F1 + A1–A6, Unit-Tests)
uv run pytest tests/moodle -q                     # Moodle (Fake-Moodle)
uv run python tests/harness/ux_check.py . --spec-only   # UX01/06/07 aus docs/UX.md
uv run python tests/acceptance/leak_check.py "<geheimnis>" ~/.config/ilias-cli   # Secret-Leak-Check
```

Exit-Codes: 0 OK · 1 Auth-Fehler/sonstiges · 2 nicht eingeloggt · 3 Session abgelaufen · 4 Netzwerk/Server · 5 Parser-Fehler.
