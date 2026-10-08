"""Dünne CLI-Hülle: Typer-Kommandos, JSON-Ausgabe, Exit-Codes (INTERFACE.md).

Keine Logik hier: Auflösen der Instanz, Login/Status/Logout und die Fehler->Exit-Code-
Abbildung kommen aus `ilias_core`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.tree import Tree

from ilias_core import (
    CoreError,
    ErrorResult,
    Service,
    __version__,
    open_service,
)
from ilias_core.models import LoginResult, LogoutResult, StatusResult

app = typer.Typer(
    help="ilias-cli – Login/Status/Logout für ILIAS- und Moodle-Instanzen (Hochschulen).",
    no_args_is_help=True,
)

err_console = Console(stderr=True, highlight=False, soft_wrap=True)
out_console = Console(highlight=False, soft_wrap=True)

_MOD_ICONS = {
    "folder": ("📁", "Ordner"),
    "resource": ("📄", "Datei"),
    "assign": ("📝", "Aufgabe"),
    "forum": ("💬", "Forum"),
    "url": ("🔗", "Link"),
    "quiz": ("❓", "Test"),
    "page": ("📃", "Seite"),
    "label": ("🏷️", "Label"),
    "choice": ("📊", "Abstimmung"),
    "lti": ("🔗", "Externes Tool"),
}
_DEFAULT_ICON = ("🔹", "Modul")

_SECTION_DEFAULT_NAMES = {"", "allgemeines", "general", "abschnitt 0"}


def _human_size(size: int | None) -> str:
    if size is None:
        return ""
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{max(1, round(size / 1024))} KB"

def _instance_option() -> Any:
    return typer.Option(
        None,
        "--instance",
        "-i",
        help="Instanz-Schlüssel aus config.toml (z. B. hhn, hs-mannheim).",
    )


def _json_option() -> Any:
    return typer.Option(
        False, "--json", help="Maschinenlesbare Ausgabe (ein JSON-Objekt auf stdout)."
    )


# ---------------------------------------------------------------- Hilfen
def _dump(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _fail(
    command: str,
    exc: CoreError,
    json_output: bool,
    service: Service | None = None,
) -> typer.Exit:
    """Fehler melden: JSON auf stdout (maschinenlesbar), Text auf stderr."""
    result = ErrorResult(
        command=command,
        error_code=exc.code,
        message=exc.message,
        exit_code=exc.exit_code,
        hint=exc.hint,
        instance=service.instance.key if service else None,
        lms=service.instance.lms if service else None,
        candidates=getattr(exc, "candidates", None),
    )
    if json_output:
        _dump(result.to_json_dict())
    err_console.print(f"[bold red]Fehler:[/bold red] {escape(exc.message)}")
    if exc.hint:
        err_console.print(f"[dim]Hinweis:[/dim] {escape(exc.hint)}")
    err_console.print(f"[dim]Exit-Code {exc.exit_code} (siehe INTERFACE.md)[/dim]")
    return typer.Exit(code=exc.exit_code)


def _version_callback(value: bool) -> None:
    if value:
        out_console.print(f"ilias-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Version anzeigen."
    ),
) -> None:
    """ilias-cli: Anmeldung an Hochschul-Lernplattformen (ILIAS, Moodle)."""


def _session_table(result: LoginResult | StatusResult) -> Table:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_row("Instanz", escape(f"{result.instance} ({result.lms})"))
    table.add_row("Server", escape(result.base_url))
    table.add_row("Angemeldet als", escape(result.username))
    if result.fullname:
        table.add_row("Name", escape(result.fullname))
    if result.sitename:
        table.add_row("Plattform", escape(result.sitename))
    if result.userid is not None:
        table.add_row("User-ID", str(result.userid))
    table.add_row("Token", "gespeichert (nicht ausgegeben)")
    table.add_row("Zeitpunkt", result.timestamp)
    return table


# ---------------------------------------------------------------- Befehle
def _run(command: str, json_output: bool, instance: str | None, op: Callable[[Service], Any]) -> Any:
    """Eine Core-Operation ausführen und Fehler -> Exit-Code (INTERFACE.md §3).

    Unerwartete Ausnahmen werden bewusst nur als Typname gemeldet: ein Traceback
    könnte Werte lokaler Variablen enthalten (A1).
    """
    service: Service | None = None
    try:
        service = open_service(instance)
        return op(service)
    except CoreError as exc:
        raise _fail(command, exc, json_output, service) from None
    except KeyboardInterrupt:  # pragma: no cover
        raise typer.Exit(code=130) from None
    except Exception as exc:
        raise _fail(
            command,
            CoreError(f"Unerwarteter Fehler: {type(exc).__name__}"),
            json_output,
            service,
        ) from None


@app.command()
def login(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Anmelden und Session speichern (fragt Benutzername und Passwort verdeckt ab)."""
    result: LoginResult = _run("login", json_output, instance, lambda service: service.login())
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print("[green]Anmeldung erfolgreich[/green]")
    out_console.print(_session_table(result))


@app.command()
def status(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Gespeicherte Session prüfen (Exit 2: keine Session, Exit 3: abgelaufen)."""
    result: StatusResult = _run("status", json_output, instance, lambda service: service.status())
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print(f"[green]Session gültig[/green] ({result.instance}, {result.lms})")
    out_console.print(_session_table(result))


@app.command()
def logout(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Gespeicherte Session lokal löschen (Keyring und Datei)."""
    result: LogoutResult = _run("logout", json_output, instance, lambda service: service.logout())
    if json_output:
        _dump(result.to_json_dict())
        return
    if result.token_removed:
        out_console.print(f"Session für {result.instance} ({result.lms}) gelöscht.")
    else:
        out_console.print(f"Keine gespeicherte Session für {result.instance} ({result.lms}) - nichts zu tun.")
    out_console.print(f"[dim]{result.timestamp}[/dim]")


# ---------------------------------------------------------------- F2/F3
@app.command()
def courses(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Eigene Kurse der Instanz auflisten (ID, Kurzname, Name, Semester)."""
    result = _run("courses", json_output, instance, lambda service: service.courses())
    if json_output:
        _dump(result.to_json_dict())
        return
    table = Table(title=f"Kurse ({result.instance}, {result.lms})")
    table.add_column("ID", justify="right")
    table.add_column("Kurzname")
    table.add_column("Name")
    table.add_column("Semester")
    for course in result.courses:
        table.add_row(
            str(course.id),
            escape(course.shortname),
            escape(course.fullname),
            escape(course.semester or "–"),
        )
    out_console.print(table)


def _markers(visible: bool, uservisible: bool, availability: str | None) -> str:
    text = ""
    if not uservisible:
        text += escape(" [gesperrt]")
        if availability:
            text += f" – {escape(availability)}"
    if not visible:
        text += escape(" [verborgen]")
    return text


def _node_label(node) -> str:
    if node.type == "folder":
        return f"📁 {escape(node.name)}"
    if node.type == "url":
        target = f" → {escape(node.url)}" if node.url else ""
        return f"🔗 {escape(node.name)}{target}"
    size = f" ({_human_size(node.size)})" if node.size is not None else ""
    return f"📄 {escape(node.name)}{size}"


@app.command(name="ls")
def ls(
    kurs: str,
    instance: str | None = _instance_option(),
    depth: int | None = typer.Option(None, "--depth", help="Tiefe: 1=Abschnitte, 2=+Module, 3=+Dateien, ab 4 pro Ordner­ebene mehr. Standard: alles."),
    json_output: bool = _json_option(),
) -> None:
    """Inhalt eines Kurses als Baum (Abschnitte, Module, Ordner, Dateien)."""
    if depth is not None and depth < 1:
        raise typer.BadParameter("--depth muss mindestens 1 sein.")
    result = _run("ls", json_output, instance, lambda service: service.ls(kurs, depth))
    if json_output:
        _dump(result.to_json_dict())
        return
    course = result.course
    root = Tree(
        f"[bold]{escape(course['fullname'])}[/bold] ({escape(course['shortname'])}) [dim]#{course['id']}[/dim]"
    )
    for section in result.sections:
        if not section.modules and section.name.strip().lower() in _SECTION_DEFAULT_NAMES:
            continue  # leere Abschnitte ohne Titel weglassen (JSON enthält sie)
        title = escape(section.name) if section.name else f"[dim]Abschnitt {section.number}[/dim]"
        branch = root.add(f"📂 {title}{_markers(section.visible, section.uservisible, None)}")
        for module in section.modules:
            icon, _kind = _MOD_ICONS.get(module.modname, _DEFAULT_ICON)
            label = f"{icon} {escape(module.name)}"
            if module.modname and module.modname not in _MOD_ICONS:
                label += f" [dim]({escape(module.modname)})[/dim]"
            mbranch = branch.add(label + _markers(module.visible, module.uservisible, module.availability))
            for node in module.children:
                _add_node(mbranch, node)
    out_console.print(root)


def _add_node(branch, node) -> None:
    nb = branch.add(_node_label(node))
    for child in node.children:
        _add_node(nb, child)


def main_entrypoint() -> None:  # pragma: no cover - Einstieg über Konsolen-Skript
    app()


if __name__ == "__main__":  # pragma: no cover
    main_entrypoint()
