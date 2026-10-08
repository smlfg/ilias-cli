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
from ilias_core.models import CourseContentsResult, CoursesResult, LoginResult, LogoutResult, StatusResult

app = typer.Typer(
    help="ilias-cli – Login/Status/Logout für ILIAS- und Moodle-Instanzen (Hochschulen).",
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
    candidates = getattr(exc, "candidates", None)
    result = ErrorResult(
        command=command,
        error_code=exc.code,
        message=exc.message,
        exit_code=exc.exit_code,
        hint=exc.hint,
        instance=service.instance.key if service else None,
        lms=service.instance.lms if service else None,
        candidates=candidates,
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


# ---------------------------------------------------------------- F2: courses
def _format_size(size: int) -> str:
    """Formatiert Bytes in KB/MB."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _courses_table(result: CoursesResult) -> Table:
    table = Table(title=f"Kurse ({result.instance}, {result.lms})", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Kurzname", style="green")
    table.add_column("Name", style="white")
    table.add_column("Semester", style="yellow")
    for course in result.courses:
        table.add_row(
            str(course.id),
            escape(course.shortname),
            escape(course.fullname),
            escape(course.semester or ""),
        )
    return table


@app.command()
def courses(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Eigene Kurse auflisten (ID, Kurzname, Name, Semester)."""
    result: CoursesResult = _run("courses", json_output, instance, lambda service: service.courses())
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print(_courses_table(result))


# ---------------------------------------------------------------- F3: ls
def _modname_icon(modname: str) -> str:
    """Gibt ein Icon für den Modul-Typ zurück."""
    icons = {
        "folder": "📁",
        "resource": "📄",
        "url": "🔗",
        "assign": "📝",
        "forum": "💬",
        "quiz": "❓",
        "page": "📃",
        "label": "🏷️",
        "choice": "☑️",
        "lti": "🔧",
    }
    return icons.get(modname, "📦")


def _modname_label(modname: str) -> str:
    """Gibt ein deutsches Label für den Modul-Typ zurück."""
    labels = {
        "folder": "Ordner",
        "resource": "Datei",
        "url": "Link",
        "assign": "Aufgabe",
        "forum": "Forum",
        "quiz": "Test",
        "page": "Seite",
        "label": "Text",
        "choice": "Abstimmung",
        "lti": "LTI-Tool",
    }
    return labels.get(modname, modname)


def _build_tree(result: CourseContentsResult) -> Tree:
    """Baut einen rich Tree aus dem Kursinhalt."""
    course_name = f"{result.course['shortname']} – {result.course['fullname']}"
    root = Tree(f"📚 [bold]{escape(course_name)}[/bold] (ID: {result.course['id']})")
    
    for section in result.sections:
        # Section-Name: falls leer oder "Abschnitt X", Nummer verwenden
        sec_name = section.name.strip()
        if not sec_name or sec_name.lower().startswith("abschnitt "):
            sec_name = f"Abschnitt {section.number}" if section.number > 0 else "Allgemeines"
        
        # Sichtbarkeits-Marker
        markers = []
        if not section.visible:
            markers.append("[verborgen]")
        if not section.uservisible:
            markers.append("[gesperrt]")
        marker_str = " ".join(markers)
        if marker_str:
            marker_str = f" [dim]{marker_str}[/dim]"
        
        section_node = root.add(f"📂 [bold]{escape(sec_name)}[/bold]{marker_str} (ID: {section.id})")
        
        for module in section.modules:
            icon = _modname_icon(module.modname)
            label = _modname_label(module.modname)
            
            markers = []
            if not module.visible:
                markers.append("[verborgen]")
            if not module.uservisible:
                markers.append("[gesperrt]")
            if module.availability:
                markers.append(f"[{escape(module.availability)}]")
            marker_str = " ".join(markers)
            if marker_str:
                marker_str = f" [dim]{marker_str}[/dim]"
            
            module_node = section_node.add(
                f"{icon} [bold]{escape(module.name)}[/bold] ({label}){marker_str}"
            )
            
            # Kinder (Dateien, Ordner, URLs)
            for child in module.children:
                if hasattr(child, 'children'):  # CourseFolder
                    _add_folder_to_tree(module_node, child)
                elif hasattr(child, 'size'):  # CourseFile
                    size_str = _format_size(child.size)
                    mime = f" ({child.mimetype})" if child.mimetype else ""
                    module_node.add(f"📄 {escape(child.name)} [dim]{size_str}{mime}[/dim]")
                elif hasattr(child, 'url'):  # CourseURL
                    module_node.add(f"🔗 {escape(child.name)} [dim]({escape(child.url)})[/dim]")
    
    return root


def _add_folder_to_tree(parent: Tree, folder, depth: int = 0) -> None:
    """Fügt einen Ordner rekursiv zum Tree hinzu."""
    folder_node = parent.add(f"📁 {escape(folder.name)}")
    for child in folder.children:
        if hasattr(child, 'children'):  # CourseFolder
            _add_folder_to_tree(folder_node, child, depth + 1)
        elif hasattr(child, 'size'):  # CourseFile
            size_str = _format_size(child.size)
            mime = f" ({child.mimetype})" if child.mimetype else ""
            folder_node.add(f"📄 {escape(child.name)} [dim]{size_str}{mime}[/dim]")
        elif hasattr(child, 'url'):  # CourseURL
            folder_node.add(f"🔗 {escape(child.name)} [dim]({escape(child.url)})[/dim]")


@app.command()
def ls(
    kurs: str = typer.Argument(..., help="Kurs-ID oder Teil des Kursnamens/Kurznamens."),
    instance: str | None = _instance_option(),
    depth: int | None = typer.Option(None, "--depth", "-d", help="Tiefe: 1=Abschnitte, 2=+Module, 3=+Dateien, ..."),
    json_output: bool = _json_option(),
) -> None:
    """Inhalt eines Kurses als Baum anzeigen (Abschnitte, Module, Dateien)."""
    result: CourseContentsResult = _run(
        "ls", json_output, instance, lambda service: service.ls(kurs, depth)
    )
    if json_output:
        _dump(result.to_json_dict())
        return
    tree = _build_tree(result)
    out_console.print(tree)


def main_entrypoint() -> None:  # pragma: no cover - Einstieg über Konsolen-Skript
    app()


if __name__ == "__main__":  # pragma: no cover
    main_entrypoint()
