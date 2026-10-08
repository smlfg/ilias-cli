# Akzeptanz-Ergebnis: attempt/longcat-2.5-preview

Modell: `opencode/longcat-2.5-preview-free` (OpenCode). Quelle: /workspace/ilias-cli-mcp/attempts/longcat-2.5-preview

Lauf: `uv run pytest tests/acceptance -q -rA` am 08.10.2026 07:22 (Europe/Berlin), Box, Python 3.11.

| Bestanden | Fehlgeschlagen | Übersprungen | Eigene Tests (tests/attempt) |
|---|---|---|---|
| 32 | 4 | 0 | 49 passed, 7 warnings in 0.33s |

## Fehlgeschlagene Akzeptanztests

- `test_wrong_totp`
- `test_server_error_during_login_exit_4`
- `test_status_server_error_exit_4`
- `test_logout_without_session_ok`

## Glue (nur Anpassung an INTERFACE.md, keine Logik-Fixes)

(1) pyproject.toml: `[dependency-groups] dev = ["pytest>=8.0"]` ergänzt (pytest war nur optionales Extra, `uv sync` installierte es nicht). (2) src/ilias_core/config.py: `ILIAS_CLI_CONFIG_DIR` zusätzlich zu `ILIAS_CLI_CONFIG` (Dateipfad) unterstützt, mit # GLUE markiert. Sonst unverändert.
