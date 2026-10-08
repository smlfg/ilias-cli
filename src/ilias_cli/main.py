"""Dünne CLI-Hülle (Skeleton). Siehe INTERFACE.md für den Vertrag."""

import typer

app = typer.Typer(help="ILIAS-CLI (Skeleton)", no_args_is_help=True)


def _not_implemented() -> None:
    typer.echo("Nicht implementiert (Skeleton auf main).", err=True)
    raise typer.Exit(code=1)


@app.command()
def login(json_output: bool = typer.Option(False, "--json")) -> None:
    """Login (OIDC/Keycloak + TOTP)."""
    _not_implemented()


@app.command()
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    """Session prüfen."""
    _not_implemented()


@app.command()
def logout(json_output: bool = typer.Option(False, "--json")) -> None:
    """Session löschen."""
    _not_implemented()
