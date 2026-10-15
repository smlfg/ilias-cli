# ilias-cli

Kommandozeilen-Tool für die Lernplattformen **ILIAS** (Hochschule Heilbronn, Uni Mannheim) und
**Moodle** (Hochschule Mannheim): anmelden, Kurse auflisten, Kursinhalt als Baum anzeigen und
Dateien herunterladen. Ein MCP-Server auf derselben Basis ist als nächster Schritt geplant.

## Status

[![ci](https://github.com/smlfg/ilias-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/smlfg/ilias-cli/actions/workflows/ci.yml)

Version 0.1.0. Login, `courses` und `ls` laufen auf allen drei Instanzen; `download` nur auf ILIAS.
Auf `uni-mannheim` ist `download` noch nicht an einem echten Server getestet.

## Schnellstart

Voraussetzungen: Python 3.11 oder neuer und [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/smlfg/ilias-cli.git
cd ilias-cli
uv sync
uv run ilias --help
uv run ilias login --instance hhn
uv run ilias courses
```

## Befehle

| Befehl | Zweck |
|---|---|
| `ilias login` | Anmelden (ILIAS: OIDC/Keycloak oder SAML/Shibboleth; Moodle: Webservice-Token) |
| `ilias status` | Gespeicherte Session prüfen (Exit 2: keine Session, Exit 3: abgelaufen) |
| `ilias logout` | Gespeicherte Session bzw. Token der Instanz lokal löschen |
| `ilias courses` | Eigene Kurse auflisten (ID, Kurzname, Name, Semester) |
| `ilias ls <kurs>` | Inhalt eines Kurses als Baum (Abschnitte, Module, Dateien) |
| `ilias download <kurs> [pfad]` | Dateien eines Kurses herunterladen, nur neue oder geänderte (nur ILIAS) |

Alle Befehle kennen `--instance/-i`, `--json` (maschinenlesbare Ausgabe) und `--debug`
(sicheres Log auf stderr: nur URLs ohne Query-Werte, Statuscodes und Formularfeld-Namen).
`login --browser` meldet sich bei ILIAS in einem sichtbaren Browser an; dafür vorher
`uv sync --extra browser && uv run playwright install chromium`.

## Instanzen

`ilias_core` hat ein Backend pro Plattform (`ilias_core.backends`: `IliasBackend`,
`MoodleBackend`) und eine Instanz-Registry in `ilias_core.config`. Eingebaut sind:

| `--instance` | LMS | Login | Befehle |
|---|---|---|---|
| `hhn` (Default) | ILIAS | OIDC/Keycloak (+ TOTP) | login, status, logout, courses, ls, download |
| `uni-mannheim` | ILIAS | SAML/Shibboleth | login, status, logout, courses, ls, download (ungetestet) |
| `hs-mannheim` | Moodle | Webservice-Token (`moodle_mobile_app`) | login, status, logout, courses, ls |

```bash
ilias login  --instance hhn                 # ILIAS HHN
ilias login  --instance hs-mannheim         # Moodle: Benutzername + Passwort (verdeckt)
ilias status --instance hs-mannheim --json
ilias courses --instance hs-mannheim
ilias ls PR1 --instance hs-mannheim --depth 2
ilias logout --instance hs-mannheim
```

### Download (nur ILIAS)

```bash
ilias download 900101 -o ~/Studium                    # ganzer Kurs -> ~/Studium/<Kursname>/<Ordner>/…
ilias download "KI-Programmierung" "Übungsblätter"    # nur ein Ordner (Pfad relativ zum Kurs)
ilias download 900101 900311                          # eine Datei per ref_id (aus `ilias ls --json`)
ilias download 900101 -n                              # --dry-run: nur anzeigen
```

- Ein zweiter Lauf lädt nur neue oder in ILIAS geänderte Dateien (Manifest `.ilias-download.json`
  im Kursordner). Von Hand abgelegte Dateien mit gleichem Namen werden nicht überschrieben;
  `--force` lädt trotzdem neu.
- Offline-Objekte werden übersprungen. Einzelne verweigerte Dateien stehen als `failed` in der
  Ausgabe, der Rest wird geladen, Exit-Code dann 1.
- `--json`: `{ok, course, target_dir, summary{downloaded,skipped,planned,failed}, items[{ref_id,name,path,status,size,error_code,message}]}`.
- Abschnitte der Kursseite („Inhalt“, Objektblöcke) werden nicht zu Ordnern, nur ILIAS-Ordner/Gruppen.

## Konfiguration

- Konfigurationsdatei: `~/.config/ilias-cli/config.toml`, oder der Ordner aus der Umgebungsvariable
  `ILIAS_CLI_CONFIG_DIR`.
- Jedes Profil lässt sich dort unter `[instances.<key>]` überschreiben oder neu anlegen
  (`lms = "ilias" | "moodle"`, `base_url`, bei ILIAS zusätzlich `client_id`, `auth`).
  Der Schlüssel `instance` wählt die aktive Instanz.
- Sessions und Tokens liegen bevorzugt im Schlüsselbund des Betriebssystems (`keyring`), sonst in
  einer Datei mit Rechten `0600` im Konfigurationsordner. Nie im Arbeitsverzeichnis, in der
  JSON-Ausgabe oder im Log.

## Aufbau

- `src/ilias_core/`: Logik ohne CLI (Konfiguration, Login-Verfahren, Session-Speicher,
  Backends für ILIAS und Moodle, Download).
- `src/ilias_cli/`: dünne Typer-Oberfläche, Einstiegspunkt `ilias`.
- Anforderungen: [ANFORDERUNGEN.md](ANFORDERUNGEN.md), Vertrag: [INTERFACE.md](INTERFACE.md),
  Moodle-Details: [MOODLE.md](MOODLE.md).

## Entwicklung und Tests

Alle Tests laufen nur gegen localhost-Fake-Server; eine Netzwerk-Sperre lässt jeden Test
scheitern, der einen echten Server erreichen will.

```bash
uv sync
uv run pytest tests/acceptance tests/attempt -q   # ILIAS (Login-Vertrag F1 + A1–A6, Unit-Tests)
uv run pytest tests/moodle -q                     # Moodle (Fake-Moodle)
uv run pytest tests/hhn tests/hhn_unit -q         # HHN: courses, ls, download (läuft nicht in CI)
uvx ruff check --select E4,E7,E9,F .              # Lint wie in CI
uv run python tests/acceptance/leak_check.py "<geheimnis>" ~/.config/ilias-cli   # Secret-Leak-Check
```

CI (`.github/workflows/ci.yml`) führt Lint, `tests/acceptance`, `tests/attempt` und `tests/moodle`
aus; ein PII-/Secret-Check läuft in `.github/workflows/pii-guard.yml`.

Exit-Codes: 0 OK · 1 Auth-Fehler/sonstiges · 2 nicht eingeloggt · 3 Session abgelaufen ·
4 Netzwerk/Server · 5 Parser-Fehler.

## Grenzen

- `download` gibt es nur für ILIAS, nicht für Moodle.
- `download` auf `uni-mannheim` ist ungetestet.
- Mehrere HHN-Tests sind als `xfail` markiert („noch nicht implementiert“); mit `HHN_STRICT=1`
  werden sie hart geprüft.

## Lizenz

Noch keine Lizenzdatei im Repository; ohne Lizenz gelten standardmäßig alle Rechte als
vorbehalten. `pyproject.toml` nennt MIT, das ist noch nicht durch eine `LICENSE`-Datei bestätigt.
