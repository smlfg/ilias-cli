# ILIAS CLI

Command-line interface for ILIAS (HHN) - Login, Status, Logout.

## Installation

```bash
uv sync
```

Or with browser fallback support:
```bash
uv sync --extra browser
```

## Commands

### `ilias login`

Login to ILIAS with HHN account (includes 2FA/TOTP).

```bash
# Interactive login (prompts for username, password, TOTP)
ilias login

# With username provided
ilias login --username max.muster

# JSON output (machine-readable)
ilias login --json --username max.muster

# Browser fallback (visible Playwright browser)
ilias login --browser --username max.muster
```

**Security:**
- Password is never stored, logged, or displayed
- Password input is hidden (TTY)
- TOTP code is prompted interactively
- No `--password` flag exists
- Session cookies stored in OS keyring (or file with 0600 permissions)

### `ilias status`

Check current session status.

```bash
# Human-readable output
ilias status

# JSON output
ilias status --json
```

### `ilias logout`

Logout and delete stored session.

```bash
ilias logout
ilias logout --json
```

### `ilias config-show`

Show current configuration.

```bash
ilias config-show
ilias config-show --json
```

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | OK | Command completed successfully |
| 1 | General Error | Generic error (invalid usage, browser not available, etc.) |
| 2 | Not Logged In | No valid session found |
| 3 | Session Expired | Session exists but has expired (redirect to login) |
| 4 | Network/Server Error | HTTP error, connection failed, timeout |
| 5 | Parser Error | Unexpected HTML structure, parsing failed |

## Configuration

Config file: `~/.config/ilias-cli/config.toml` (or `$ILIAS_CLI_CONFIG_DIR/config.toml`)

```toml
base_url = "https://ilias.hs-heilbronn.de"
client_id = "iliashhn"
session_store = "auto"  # auto, keyring, file
timeout = 30.0
```

Environment variables:
- `ILIAS_CLI_CONFIG_DIR` - Override config directory
- `ILIAS_CLI_CONFIG_FILE` - Override config file path

## Session Storage

- **Primary**: OS keyring (macOS Keychain, Linux Secret Service, Windows Credential Manager)
- **Fallback**: File at `~/.config/ilias-cli/session.json` with 0600 permissions
- Cookies are never logged or included in JSON output

## Development

### Run tests

```bash
uv run pytest -q
```

### Type checking

```bash
uv run mypy src/
```

### Linting

```bash
uv run ruff check src/
```

## Architecture

```
src/
├── ilias_core/          # Core library (used by CLI and future MCP server)
│   ├── config.py        # Configuration management
│   ├── errors.py        # Exception hierarchy with exit codes
│   ├── models.py        # Pydantic data models
│   ├── session.py       # Session storage (keyring + file)
│   └── auth.py          # Keycloak/OIDC auth flow, form parsers
└── ilias_cli/           # Thin CLI wrapper
    └── main.py          # Typer commands, rich output
```

## Security Notes

- **A1**: Password never stored, logged, printed, or in exceptions
- **A2**: TOTP prompted interactively, no secret stored
- **A3**: Headless login via httpx (Keycloak forms), browser fallback with Playwright
- **A4**: Session cookies in OS keyring or 0600 file, never in output
- **A5**: Status checks session via protected page, no auto-re-login
- **A6**: Session per device, no cookie sync