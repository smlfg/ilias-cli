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
