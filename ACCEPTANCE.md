# Akzeptanz-Ergebnis: attempt/deepseek-v4.1-flash

Modell: `opencode-go/deepseek-v4.1-flash` (OpenCode). Quelle: /workspace/ilias-cli-mcp/attempts/deepseek-v4.1-flash

Lauf: `uv run pytest tests/acceptance -q -rA` am 08.10.2026 07:22 (Europe/Berlin), Box, Python 3.11.

| Bestanden | Fehlgeschlagen | Übersprungen | Eigene Tests (tests/attempt) |
|---|---|---|---|
| 35 | 1 | 0 | 29 passed in 0.45s |

## Fehlgeschlagene Akzeptanztests

- `test_unexpected_html_exit_5`

## Glue (nur Anpassung an INTERFACE.md, keine Logik-Fixes)

Keiner. Code, pyproject.toml und uv.lock unverändert übernommen; eigene Tests nach tests/attempt/ verschoben, README nach README.attempt.md.
