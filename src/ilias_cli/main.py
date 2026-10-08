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
from rich.text import Text
from rich.tree import Tree

from ilias_core import (
    CoreError,
    ErrorResult,
    Service,
    __version__,
    open_service,
)
from ilias_core.models import (
    ContentNode,
    CourseContentsResult,
    CourseListResult,
    FileNode,
    FolderNode,
    LoginResult,
    LogoutResult,
    ModuleNode,
    SectionNode,
    StatusResult,
    UrlNode,
)

app = typer.Typer(
    help="ilias-cli – Login/Status/Logout und Kurse (courses/ls) für ILIAS- und Moodle-Instanzen.",
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
        details=exc.details or None,
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


# ------------------------------------------------- Kurse (F2/F3): nur Darstellung
# Symbole/Typnamen sind reine Formatierung; die Logik liegt in ilias_core.
MODULE_ICONS: dict[str, str] = {
    "folder": "📁 Ordner",
    "resource": "📄 Datei",
    "url": "🔗 Link",
    "assign": "📝 Aufgabe",
    "forum": "💬 Forum",
    "quiz": "❓ Test",
    "page": "📃 Seite",
    "label": "🏷 Hinweis",
    "choice": "☑ Umfrage",
    "lti": "🔌 Externe App",
    "book": "📖 Buch",
    "wiki": "📝 Wiki",
}
DEFAULT_MODULE_ICON = "📦 Modul"
MARKER_HIDDEN = "[verborgen]"
MARKER_LOCKED = "[gesperrt]"


def human_size(size: int | None) -> str:
    """Dateigröße für Menschen (Bytes/KB/MB)."""
    if size is None:
        return "?"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def module_icon(module: ModuleNode) -> str:
    return MODULE_ICONS.get(module.modname, f"{DEFAULT_MODULE_ICON} {module.modname}".strip())


def _mark_flags(text: Text, *, visible: bool, uservisible: bool) -> None:
    """Verborgene und gesperrte Elemente bleiben sichtbar, nur markiert."""
    if not uservisible:
        text.append(f" {MARKER_LOCKED}", style="yellow")
    if not visible:
        text.append(f" {MARKER_HIDDEN}", style="yellow")


def _section_label(section: SectionNode) -> Text:
    label = Text()
    label.append(f"{section.number}. ", style="bold")
    label.append(section.name or "Allgemeines")
    _mark_flags(label, visible=section.visible, uservisible=section.uservisible)
    return label


def _module_label(module: ModuleNode) -> Text:
    label = Text()
    label.append(f"{module_icon(module)} ", style="cyan")
    label.append(module.name)
    _mark_flags(label, visible=module.visible, uservisible=module.uservisible)
    if module.availability:
        label.append(f" - {module.availability}", style="dim")
    return label


def _content_label(node: ContentNode) -> Text:
    label = Text()
    if isinstance(node, FileNode):
        label.append("📄 Datei ", style="cyan")
        label.append(node.name)
        label.append(f" ({human_size(node.size)})", style="dim")
        if node.timemodified:
            label.append(f" {node.timemodified[:10]}", style="dim")
    elif isinstance(node, UrlNode):
        label.append("🔗 Link ", style="cyan")
        label.append(node.name)
        label.append(f" {node.url}", style="dim")
    elif isinstance(node, FolderNode):
        label.append("📁 Ordner ", style="cyan")
        label.append(node.name)
    else:  # pragma: no cover - kein weiterer Knotentyp
        label.append(str(getattr(node, "name", node)))
    return label


def _add_contents(branch: Tree, nodes: tuple[ContentNode, ...]) -> None:
    for node in nodes:
        child = branch.add(_content_label(node))
        if isinstance(node, FolderNode):
            _add_contents(child, node.children)


def courses_table(result: CourseListResult) -> Table:
    """F2: Tabelle der eigenen Kurse (Sortierung kommt aus ilias_core)."""
    table = Table(title=f"Eigene Kurse ({result.instance}, {result.lms})")
    table.add_column("ID", justify="right")
    table.add_column("Kurzname")
    table.add_column("Name")
    table.add_column("Semester")
    for course in result.courses:
        table.add_row(
            str(course.id),
            escape(course.shortname),
            escape(course.fullname),
            escape(course.semester or "unbekannt"),
        )
    return table


def course_tree(result: CourseContentsResult) -> Tree:
    """F3: Kurs als Baum (Abschnitte -> Module -> Ordner/Dateien/Links)."""
    root = Text()
    root.append(result.course.shortname, style="bold")
    root.append(" · ", style="dim")
    root.append(result.course.fullname)
    root.append(f"  (Kurs-ID {result.course.id})", style="dim")
    tree = Tree(root, guide_style="dim")

    for section in result.sections:
        if not section.modules:
            continue  # leere Abschnitte stehen nur in der JSON-Ausgabe
        branch = tree.add(_section_label(section))
        for module in section.modules:
            module_branch = branch.add(_module_label(module))
            _add_contents(module_branch, module.children)
    return tree


def _count_modules(sections: tuple[SectionNode, ...]) -> int:
    return sum(len(section.modules) for section in sections)


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


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


@app.command()
def courses(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Eigene Kurse auflisten (Tabelle oder JSON), neuestes Semester zuerst."""
    result: CourseListResult = _run("courses", json_output, instance, lambda service: service.courses())
    if json_output:
        _dump(result.to_json_dict())
        return
    if not result.courses:
        out_console.print(f"Keine Kurse für {result.instance} ({result.lms}).")
        out_console.print(f"[dim]{result.timestamp}[/dim]")
        return
    out_console.print(courses_table(result))
    out_console.print(f"[dim]{_plural(result.count, 'Kurs', 'Kurse')} · {result.instance} · {result.timestamp}[/dim]")


@app.command()
def ls(
    kurs: str = typer.Argument(
        ...,
        metavar="<kurs>",
        help="Kurs-ID (z. B. 51234) oder ein Stück aus Kurzname/Titel (z. B. PR1-WS26).",
    ),
    instance: str | None = _instance_option(),
    depth: int | None = typer.Option(
        None,
        "--depth",
        min=1,
        help="Tiefe begrenzen: 1 = nur Abschnitte, 2 = + Module, 3 = + Dateien/Ordner. "
        "Vorgabe: unbegrenzt.",
    ),
    json_output: bool = _json_option(),
) -> None:
    """Inhalt eines Kurses als Baum anzeigen (Abschnitte, Module, Dateien)."""
    result: CourseContentsResult = _run("ls", json_output, instance, lambda service: service.ls(kurs, depth))
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print(course_tree(result))
    out_console.print(
        f"[dim]{_plural(len(result.sections), 'Abschnitt', 'Abschnitte')} · "
        f"{_plural(_count_modules(result.sections), 'Modul', 'Module')} · "
        f"Tiefe {depth if depth is not None else 'unbegrenzt'} · {result.timestamp}[/dim]"
    )


def main_entrypoint() -> None:  # pragma: no cover - Einstieg über Konsolen-Skript
    app()


if __name__ == "__main__":  # pragma: no cover
    main_entrypoint()
