"""ILIAS CLI - Main entry point."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ilias_core import (
    AuthClient,
    BrowserNotAvailableError,
    Config,
    ILIASError,
    InvalidCredentialsError,
    InvalidTOTPError,
    LoginResult,
    LogoutResult,
    NetworkError,
    ParserError,
    SessionStatus,
    check_session_status,
    create_session_store,
    ensure_config_dir,
    load_config,
)
from ilias_core.config import get_config_path

app = typer.Typer(
    name="ilias",
    help="ILIAS CLI for HHN - Login, Status, Logout",
    add_completion=False,
    no_args_is_help=True,
)

console = Console(stderr=True)
err_console = Console(stderr=True)


def get_config(ctx: typer.Context) -> Config:
    """Load config from context or default."""
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    return load_config(config_path)


def print_json(data: dict) -> None:
    """Print JSON to stdout."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def print_error(message: str, *, json_output: bool = False) -> None:
    """Print error message."""
    if json_output:
        print_json({"error": message})
    else:
        err_console.print(f"[red]Error:[/red] {message}")


def handle_error(error: Exception, *, json_output: bool = False) -> int:
    """Handle error and return exit code."""
    from ilias_core.errors import exit_code_for_error

    if json_output:
        print_json({"error": str(error)})
    else:
        err_console.print(f"[red]Error:[/red] {error}")
    return exit_code_for_error(error)


@app.callback()
def main(
    ctx: typer.Context,
    config_file: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config file",
        envvar="ILIAS_CLI_CONFIG_FILE",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON",
    ),
) -> None:
    """ILIAS CLI for HHN."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_file
    ctx.obj["json_output"] = json_output


@app.command()
def login(
    ctx: typer.Context,
    json_flag: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),  # GLUE: --json als Unterbefehl-Option (INTERFACE.md)
    username: str | None = typer.Option(
        None,
        "--username",
        "-u",
        help="HHN username (prompts if not provided)",
    ),
    browser: bool = typer.Option(
        False,
        "--browser",
        help="Use visible browser for login (Playwright)",
    ),
) -> None:
    """Login to ILIAS with HHN account (includes 2FA)."""
    config = get_config(ctx)
    json_output = ctx.obj.get("json_output", False) or json_flag  # GLUE

    ensure_config_dir(config)
    session_store = create_session_store(config)

    # Check if already logged in
    existing = session_store.load()
    if existing:
        if not json_output:
            console.print("[yellow]Already logged in. Use 'ilias logout' first.[/yellow]")
        else:
            print_json({"error": "Already logged in"})
        raise typer.Exit(code=1)

    # Get username
    if username is None:
        if json_output:
            print_error("Username required (use --username)", json_output=True)
            raise typer.Exit(code=1)
        username = typer.prompt("HHN Username")

    # Get password (hidden input)
    if json_output:
        print_error("Password input not supported in JSON mode", json_output=True)
        raise typer.Exit(code=1)

    password = typer.prompt("Password", hide_input=True)

    # TOTP callback
    def get_totp() -> str:
        if json_output:
            print_error("TOTP input not supported in JSON mode", json_output=True)
            raise typer.Exit(code=1)
        return typer.prompt("TOTP Code (from authenticator app)", hide_input=True)

    async def run_login() -> LoginResult:
        async with AuthClient(config) as client:
            return await client.login(username, password, get_totp, browser_fallback=browser)

    try:
        result = asyncio.run(run_login())
    except InvalidCredentialsError as e:
        print_error(str(e), json_output=json_output)
        raise typer.Exit(code=1)
    except InvalidTOTPError as e:
        print_error(str(e), json_output=json_output)
        raise typer.Exit(code=1)
    except BrowserNotAvailableError as e:
        print_error(str(e), json_output=json_output)
        raise typer.Exit(code=1)
    except (NetworkError, ParserError, ILIASError) as e:
        raise typer.Exit(code=handle_error(e, json_output=json_output))
    except Exception as e:
        raise typer.Exit(code=handle_error(e, json_output=json_output))

    # Save session
    if result.cookies:
        session_store.save(result.cookies)

    if json_output:
        # Output without cookies
        print_json(result.model_dump(exclude={"cookies"}))
    else:
        console.print(Panel.fit(
            f"[green]✓[/green] {result.message}",
            title="Login Successful",
            border_style="green",
        ))
        if result.cookies:
            console.print(f"Session saved via {type(session_store).__name__}")


@app.command()
def status(
    ctx: typer.Context,
    json_flag: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),  # GLUE: --json als Unterbefehl-Option (INTERFACE.md)
) -> None:
    """Check current login session status."""
    config = get_config(ctx)
    json_output = ctx.obj.get("json_output", False) or json_flag  # GLUE

    session_store = create_session_store(config)
    cookies = session_store.load()

    if not cookies:
        result = SessionStatus(logged_in=False, message="Not logged in")
        if json_output:
            print_json(result.model_dump())
        else:
            console.print("[red]Not logged in[/red]")
        raise typer.Exit(code=2)

    async def run_check() -> SessionStatus:
        return await check_session_status(config, cookies)

    try:
        result = asyncio.run(run_check())
    except (NetworkError, ParserError, ILIASError) as e:
        raise typer.Exit(code=handle_error(e, json_output=json_output))
    except Exception as e:
        raise typer.Exit(code=handle_error(e, json_output=json_output))

    if json_output:
        print_json(result.model_dump())
    else:
        if result.logged_in:
            table = Table(show_header=False, box=None)
            table.add_column("Key", style="cyan")
            table.add_column("Value")
            table.add_row("Status", "[green]Logged in[/green]")
            if result.username:
                table.add_row("User", result.username)
            if result.expires_at:
                table.add_row("Expires", result.expires_at)
            console.print(table)
        else:
            console.print("[red]Session expired[/red]")

    if not result.logged_in:
        raise typer.Exit(code=3)


@app.command()
def logout(
    ctx: typer.Context,
    json_flag: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),  # GLUE: --json als Unterbefehl-Option (INTERFACE.md)
) -> None:
    """Logout and delete stored session."""
    config = get_config(ctx)
    json_output = ctx.obj.get("json_output", False) or json_flag  # GLUE

    session_store = create_session_store(config)
    cookies = session_store.load()

    if not cookies:
        result = LogoutResult(success=False, message="Not logged in")
        if json_output:
            print_json(result.model_dump())
        else:
            console.print("[yellow]Not logged in[/yellow]")
        raise typer.Exit(code=0)  # Not an error

    session_store.delete()

    result = LogoutResult(success=True, message="Logged out successfully")
    if json_output:
        print_json(result.model_dump())
    else:
        console.print("[green]Logged out successfully[/green]")


@app.command()
def config_show(ctx: typer.Context) -> None:
    """Show current configuration."""
    config = get_config(ctx)
    json_output = ctx.obj.get("json_output", False)

    data = {
        "base_url": config.base_url,
        "client_id": config.client_id,
        "config_dir": str(config.config_dir),
        "session_store": config.session_store,
        "timeout": config.timeout,
        "config_file": str(get_config_path()),
    }

    if json_output:
        print_json(data)
    else:
        table = Table(title="ILIAS CLI Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value")
        for k, v in data.items():
            table.add_row(k, str(v))
        console.print(table)


if __name__ == "__main__":
    app()