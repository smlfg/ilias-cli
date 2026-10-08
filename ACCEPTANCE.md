# Akzeptanz-Ergebnis: attempt/fledge-alpha

Modell: `opencode/fledge-alpha-free` (OpenCode). Quelle: /workspace/ilias-cli-mcp/attempts/fledge-alpha

Lauf: `uv run pytest tests/acceptance -q -rA` am 08.10.2026 07:22 (Europe/Berlin), Box, Python 3.11.

| Bestanden | Fehlgeschlagen | Übersprungen | Eigene Tests (tests/attempt) |
|---|---|---|---|
| 35 | 1 | 0 | 16 passed in 0.49s |

## Fehlgeschlagene Akzeptanztests

- `test_only_ilias_cookies_are_stored`

## Glue (nur Anpassung an INTERFACE.md, keine Logik-Fixes)

Keiner. Code, pyproject.toml und uv.lock unverändert übernommen (inkl. Nachlauf per --session-Follow-up); eigene Tests nach tests/attempt/, README nach README.attempt.md.
