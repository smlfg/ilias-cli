"""Dünne CLI-Hülle: Typer-Kommandos, JSON-Ausgabe, Exit-Codes (INTERFACE.md).

Keine Logik hier: Auflösen der Instanz, Login/Status/Logout und die Fehler->Exit-Code-
Abbildung kommen aus `ilias_core`.
"""

from __future__ import annotations

import json
import re
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
    FileNode,
    FolderNode,
    Service,
    UrlNode,
    __version__,
    open_service,
)
from ilias_core.models import (
    CourseContentsResult,
    CoursesResult,
    LoginResult,
    LogoutResult,
    StatusResult,
)

app = typer.Typer(
    help="ilias-cli – Login/Status/Logout, Kurse und Kursinhalte für ILIAS- und Moodle-Instanzen.",
    no_args_is_help=True,
)

err_console = Console(stderr=True, highlight=False, soft_wrap=True)
out_console = Console(highlight=False, soft_wrap=True)

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


# ---------------------------------------------------------------- F2: Kurse
def _courses_table(result: CoursesResult) -> Table:
    table = Table(title=f"Kurse ({result.instance}, {result.lms})", header_style="bold")
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Kurzname", no_wrap=True)
    table.add_column("Name")
    table.add_column("Semester", no_wrap=True)
    for course in result.courses:
        table.add_row(
            str(course.id),
            escape(course.shortname),
            escape(course.fullname),
            escape(course.semester or "—"),
        )
    return table


@app.command()
def courses(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Eigene Moodle-Kurse auflisten (ID, Kurzname, Name, Semester)."""
    result: CoursesResult = _run("courses", json_output, instance, lambda service: service.courses())
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print(_courses_table(result))
    out_console.print(f"[dim]{len(result.courses)} Kurs(e) · {result.timestamp}[/dim]")


# ---------------------------------------------------------------- F3: Kursinhalt
_MODULE_LABELS = {
    "folder": "📁 Ordner",
    "resource": "📄 Datei",
    "url": "🔗 Link",
    "assign": "📝 Aufgabe",
    "forum": "💬 Forum",
    "quiz": "❓ Test",
    "page": "📃 Seite",
    "label": "🏷️ Beschriftung",
    "choice": "🗳️ Abstimmung",
    "lti": "🔌 LTI",
    "book": "📖 Buch",
}

_DEFAULT_SECTION_RE = re.compile(
    r"^(abschnitt|thema|topic|section|bereich)\s*\d*$", re.IGNORECASE
)


def _human_size(size: int | None) -> str:
    if not size or size <= 0:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _marks(visible: bool, uservisible: bool, availability: str | None = None) -> str:
    parts: list[str] = []
    if not uservisible:
        parts.append(escape("[gesperrt]"))
        if availability:
            parts.append(f"({escape(availability)})")
    if not visible:
        parts.append(escape("[verborgen]"))
    return (" " + " ".join(parts)) if parts else ""


def _module_label(module) -> str:
    label = _MODULE_LABELS.get(module.modname, f"📦 {module.modname or 'Modul'}")
    name = escape(module.name) if module.name else "(ohne Namen)"
    return f"{label}: {name}{_marks(module.visible, module.uservisible, module.availability)}"


def _render_children(branch: Tree, children: list) -> None:
    for child in children:
        if isinstance(child, FolderNode):
            sub = branch.add(f"📁 {escape(child.name)}")
            _render_children(sub, child.children)
        elif isinstance(child, FileNode):
            size = _human_size(child.size)
            suffix = f" [dim]({size})[/dim]" if size else ""
            branch.add(f"📄 {escape(child.name)}{suffix}")
        elif isinstance(child, UrlNode):
            branch.add(f"🔗 {escape(child.name)}: {escape(child.url)}")


def _contents_tree(result: CourseContentsResult) -> Tree:
    course = result.course
    root = Tree(
        f"[bold]{escape(str(course.get('fullname', '')))}[/bold] "
        f"([dim]{escape(str(course.get('shortname', '')))}[/dim])"
    )
    for section in result.sections:
        if not section.modules and (
            not section.name.strip() or _DEFAULT_SECTION_RE.match(section.name)
        ):
            continue  # leere Standardabschnitte im Menschen-Text auslassen (JSON behält sie)
        section_name = escape(section.name) if section.name.strip() else f"Abschnitt {section.number}"
        branch = root.add(
            f"[bold]{section_name}[/bold]{_marks(section.visible, section.uservisible)}"
        )
        for module in section.modules:
            module_branch = branch.add(_module_label(module))
            _render_children(module_branch, module.children)
    return root


@app.command()
def ls(
    kurs: str = typer.Argument(..., help="Kurs-ID oder Teilstring von Kurzname/Name."),
    instance: str | None = _instance_option(),
    depth: int | None = typer.Option(
        None,
        "--depth",
        "-d",
        help="Baumtiefe: 1=Abschnitte, 2=+Module, 3=+Dateien/erste Ordnerebene, ... (Default: alles).",
    ),
    json_output: bool = _json_option(),
) -> None:
    """Inhalt eines Kurses als Baum zeigen (Abschnitte, Module, Dateien)."""
    if depth is not None and depth < 1:
        raise typer.BadParameter("--depth muss mindestens 1 sein.")
    result: CourseContentsResult = _run(
        "ls", json_output, instance, lambda service: service.ls(kurs, depth)
    )
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print(_contents_tree(result))
    out_console.print(f"[dim]{result.timestamp}[/dim]")


def main_entrypoint() -> None:  # pragma: no cover - Einstieg über Konsolen-Skript
    app()


if __name__ == "__main__":  # pragma: no cover
    main_entrypoint()
