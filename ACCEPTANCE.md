# Akzeptanz-Ergebnis: attempt/nemotron-3-ultra

Modell: `opencode/nemotron-3-ultra-free` (OpenCode). Quelle: /workspace/ilias-cli-mcp/attempts/nemotron-3-ultra

Lauf: `uv run pytest tests/acceptance -q -rA` am 08.10.2026 07:22 (Europe/Berlin), Box, Python 3.11.

| Bestanden | Fehlgeschlagen | Übersprungen | Eigene Tests (tests/attempt) |
|---|---|---|---|
| 34 | 2 | 0 | 74 passed, 1 skipped in 0.42s |

## Fehlgeschlagene Akzeptanztests

- `test_login_json_output`
- `test_only_ilias_cookies_are_stored`

## Glue (nur Anpassung an INTERFACE.md, keine Logik-Fixes)

src/ilias_cli/main.py: `--json` zusätzlich als Option der Unterbefehle login/status/logout (`json_output = global --json OR --json`, mit # GLUE markiert). Original kannte nur `ilias --json <cmd>`. Sonst unverändert; eigene Tests nach tests/attempt/.
