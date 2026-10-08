"""Typer-App: ``ilias`` (Entry point)."""

from __future__ import annotations

import typer
from rich.console import Console

from ilias_cli.commands.login import login_command
from ilias_cli.commands.logout import logout_command
from ilias_cli.commands.status import status_command

app = typer.Typer(
    name="ilias",
    help="ILIAS-CLI (HHN): login, status, logout.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
err_console = Console(stderr=True)


@app.callback()
def _callback() -> None:
    """ILIAS-CLI."""


app.command("login")(login_command)
app.command("status")(status_command)
app.command("logout")(logout_command)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
