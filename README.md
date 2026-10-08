# ilias-cli

CLI (später MCP-Server) für ILIAS an der Hochschule Heilbronn – und, auf dem Branch `moodle/*`, zusätzlich für **Moodle** (z. B. Hochschule Mannheim). Anforderungen: [ANFORDERUNGEN.md](ANFORDERUNGEN.md), Vertrag: [INTERFACE.md](INTERFACE.md).

`main` enthält nur den **Vertrag**: Skeleton (`ilias_core`, Kommando `ilias`), [INTERFACE.md](INTERFACE.md) und die modellunabhängige **Akzeptanz-Testsuite** unter `tests/acceptance/` für den Login-Teil (F1 + A1–A6). Die Skeleton-Befehle sind absichtlich nicht implementiert, die Suite ist auf `main` also rot.

Implementierungen verschiedener Modelle liegen auf `attempt/<modell>`-Branches und werden über die gleiche Suite verglichen.

```bash
uv sync
uv run pytest tests/acceptance -q          # Akzeptanztests (nur localhost-Fake-Server, keine echten Requests)
uv run python tests/acceptance/leak_check.py "<geheimnis>" ~/.config/ilias-cli   # Secret-Leak-Check
```

Exit-Codes: 0 OK · 1 Auth-Fehler/sonstiges · 2 nicht eingeloggt · 3 Session abgelaufen · 4 Netzwerk/Server · 5 Parser-Fehler.

## Moodle (dieser Branch)

`ilias_core` hat ein austauschbares Backend pro Plattform; gewählt wird es über den
Schlüssel `lms` in `~/.config/ilias-cli/config.toml` (`"ilias"` bleibt Default). Eingebaut
ist das Profil `hs-mannheim` (`lms = "moodle"`, `https://moodle.hs-mannheim.de`).

```bash
ilias login  --instance hs-mannheim   # Benutzername + Passwort (verdeckt), Webservice-Token
ilias status --instance hs-mannheim   # 0 = gültig, 2 = kein Token, 3 = abgelaufen
ilias logout --instance hs-mannheim   # löscht den Token lokal
ilias status --instance hs-mannheim --json
```

Details: **[MOODLE.md](MOODLE.md)** (Endpunkte, Config, Exit-Codes, Sicherheit, Tests).

```bash
uv run pytest tests/moodle -q          # eigene Tests: lokaler Fake-Moodle, harte localhost-Sperre
```