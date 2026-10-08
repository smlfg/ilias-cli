# Vergleich der Login-Attempts (Stand 08.10.2026, Europe/Berlin)

Gleicher Prompt für alle Modelle (`/workspace/ilias-cli-mcp/attempts/PROMPT.md`), gleiche Akzeptanz-Suite (`tests/acceptance`, 36 Tests). Glue-Details: `ACCEPTANCE.md` im jeweiligen Branch.

| Branch | Modell | Akzeptanz (P/F/S) | Eigene Tests | Laufzeit OpenCode | Glue |
|---|---|---|---|---|---|
| attempt/deepseek-v4.1-flash | opencode-go/deepseek-v4.1-flash | **35 / 1 / 0** | 29 passed | 10,8 min (1 Lauf) | keiner |
| attempt/fledge-alpha | opencode/fledge-alpha-free | 35 / 1 / 0 | 16 passed | 5,3 + 5,8 min (1 Follow-up) | keiner |
| attempt/nemotron-3-ultra | opencode/nemotron-3-ultra-free | 34 / 2 / 0 | 74 passed, 1 skipped | 30 min Timeout + 8,2 min | `--json` pro Unterbefehl |
| attempt/longcat-2.5-preview | opencode/longcat-2.5-preview-free | 32 / 4 / 0 | 49 passed | 30 min Timeout + 11,4 min | pytest in dev-Gruppe, `ILIAS_CLI_CONFIG_DIR` |
| attempt/muse-spark-1.3-contributor | opencode/muse-spark-1.3-contributor-free | 3 / 29 / 4 | – | 30 + 20 min Timeout (Rate-Limit) | keiner (unvollständig) |
| – | opencode/mimo-v2.6-flash-free | kein Code | – | 30 + 20 min, Rate-Limit | – |
| – | opencode/ling-3.1-flash-free | kein Code | – | Abbruch nach 1,5 min (Upstream 429) | – |

## Fehlgeschlagene Akzeptanztests
- **deepseek**: `test_unexpected_html_exit_5`: Bei unerwartetem HTML statt Keycloak-Formular meldet `login` Erfolg (Exit 0) und speichert die anonyme PHPSESSID. Ursache: „eingeloggt“ heißt nur „PHPSESSID vorhanden“.
- **fledge**: `test_only_ilias_cookies_are_stored`: speichert alle Cookies inkl. Keycloak-SSO (`KEYCLOAK_IDENTITY`, `AUTH_SESSION_ID`).
- **nemotron**: `test_login_json_output` (lehnt `login --json` grundsätzlich ab), `test_only_ilias_cookies_are_stored` (speichert Keycloak-Cookies).
- **longcat**: `test_wrong_totp` (falscher TOTP ⇒ „Login erfolgreich“ + anonyme Session gespeichert), `test_server_error_during_login_exit_4` (502 ⇒ Exit 5), `test_status_server_error_exit_4` (503 ⇒ „Eingeloggt“), `test_logout_without_session_ok` (Exit 2).
- **muse**: kein `ilias_cli.main`, das Kommando crasht.
