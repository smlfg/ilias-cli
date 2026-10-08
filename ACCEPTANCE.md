# Akzeptanz-Ergebnis: attempt/muse-spark-1.3-contributor

Modell: `opencode/muse-spark-1.3-contributor-free` (OpenCode). Quelle: /workspace/ilias-cli-mcp/attempts/muse-spark-1.3-contributor

Lauf: `uv run pytest tests/acceptance -q -rA` am 08.10.2026 07:22 (Europe/Berlin), Box, Python 3.11.

| Bestanden | Fehlgeschlagen | Übersprungen | Eigene Tests (tests/attempt) |
|---|---|---|---|
| 3 | 29 | 4 | no tests ran in 0.00s |

## Fehlgeschlagene Akzeptanztests

- `test_help_lists_commands`
- `test_each_command_has_json_flag[login]`
- `test_each_command_has_json_flag[status]`
- `test_each_command_has_json_flag[logout]`
- `test_login_full_keycloak_flow`
- `test_login_posts_form_action_and_hidden_fields`
- `test_user_agent_is_ilias_cli`
- `test_login_json_output`
- `test_wrong_password`
- `test_wrong_totp`
- `test_unexpected_html_exit_5`
- `test_network_error_exit_4`
- `test_server_error_during_login_exit_4`
- `test_status_without_session_exit_2`
- `test_status_without_session_json`
- `test_status_after_login_ok`
- `test_status_json_logged_in_without_cookies`
- `test_status_expired_exit_3_without_relogin`
- `test_status_expired_json`
- `test_status_server_error_exit_4`
- `test_status_network_error_exit_4`
- `test_logout_removes_session`
- `test_logout_without_session_ok`
- `test_session_stored_in_keyring_or_0600_file`
- `test_file_fallback_0600_without_keyring`
- `test_only_ilias_cookies_are_stored`
- `test_totp_code_not_stored`
- `test_default_config_path_in_home`
- `test_base_url_with_path_prefix`

## Glue (nur Anpassung an INTERFACE.md, keine Logik-Fixes)

Keiner. Der Versuch ist unvollständig (Rate-Limit/Timeout): ilias_core (auth, keycloak_parser, session, config, errors, models) existiert, aber kein `ilias_cli.main`, keine Tests, kein README. Das Kommando `ilias` crasht deshalb mit ModuleNotFoundError. Build klappt nur, weil das README.md von main vorhanden ist.
