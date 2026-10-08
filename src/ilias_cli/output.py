"""Ausgabe der CLI (menschlich mit rich, maschinell als JSON).

Cookies, Passwörter und Tokens dürfen hier niemals auftauchen. Alle Texte vom
Server werden mit ``rich.markup.escape`` ausgegeben (Namen wie ``[Klausur]``).
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.tree import Tree

from ilias_core.models import (
    CourseContentsResult,
    CoursesResult,
    FileNode,
    FolderNode,
    LoginResult,
    LogoutResult,
    MoodleLoginResult,
    MoodleStatusResult,
    SessionStatus,
    UrlNode,
)

console = Console()
err_console = Console(stderr=True)
# Moodle-Ausgaben: ohne Syntax-Highlighting, ohne harte Umbrüche
out_console = Console(highlight=False, soft_wrap=True)


def print_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))


def print_login(result: LoginResult) -> None:
    console.print(
        f"[green]Login erfolgreich und geprüft[/green] ({result.method}) – "
        f"{result.base_url} [dim](Instanz {result.instance}, {result.client_id})[/dim]"
    )


def print_status(status: SessionStatus) -> None:
    console.print(
        f"[green]Eingeloggt[/green] – {status.base_url} "
        f"[dim](Instanz {status.instance}, {status.client_id})[/dim]"
    )


def print_logout(removed: bool) -> None:
    if removed:
        console.print("[green]Session gelöscht.[/green]")
    else:
        console.print("Keine gespeicherte Session vorhanden.")


def print_error(message: str, hint: str | None = None) -> None:
    err_console.print(f"[bold red]Fehler:[/bold red] {escape(message)}")
    if hint:
        err_console.print(f"[dim]Hinweis:[/dim] {escape(hint)}")


def error_payload(exc: Exception, exit_code: int) -> dict[str, Any]:
    return {
        "ok": False,
        "error": type(exc).__name__,
        "exit_code": exit_code,
        "message": str(exc),
    }


# ------------------------------------------------------------- Moodle: Session
def _session_table(result: MoodleLoginResult | MoodleStatusResult) -> Table:
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


def print_moodle_login(result: MoodleLoginResult) -> None:
    out_console.print("[green]Anmeldung erfolgreich[/green]")
    out_console.print(_session_table(result))


def print_moodle_status(result: MoodleStatusResult) -> None:
    out_console.print(f"[green]Session gültig[/green] ({escape(result.instance)}, {result.lms})")
    out_console.print(_session_table(result))


def print_moodle_logout(result: LogoutResult) -> None:
    if result.token_removed:
        out_console.print(f"Session für {escape(result.instance)} ({result.lms}) gelöscht.")
    else:
        out_console.print(
            f"Keine gespeicherte Session für {escape(result.instance)} ({result.lms}) - nichts zu tun."
        )
    out_console.print(f"[dim]{result.timestamp}[/dim]")


# ------------------------------------------------------------- F2: Kurse
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


def print_courses(result: CoursesResult) -> None:
    out_console.print(_courses_table(result))
    out_console.print(f"[dim]{len(result.courses)} Kurs(e) · {result.timestamp}[/dim]")


# ------------------------------------------------------------- F3: Kursinhalt
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
    "lti": "🔌 Externes Tool",
    "book": "📖 Buch",
    "scheduler": "📅 Terminplaner",
    "feedback": "📋 Feedback",
    "glossary": "📚 Glossar",
    "wiki": "📖 Wiki",
    "lesson": "📑 Lektion",
    "workshop": "🤝 Gegenseitige Beurteilung",
    "h5pactivity": "🎮 H5P",
    "bigbluebuttonbn": "🎥 BigBlueButton",
    "data": "🗄️ Datenbank",
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


def _url_target(module) -> str | None:
    for child in module.children:
        if isinstance(child, UrlNode):
            return child.url
    return None


def _url_label(module) -> str:
    """Ein Link-Modul als genau eine Zeile: 🔗 Modulname → URL."""
    name = escape(module.name) if module.name else "(ohne Namen)"
    target = _url_target(module)
    arrow = f" → {escape(target)}" if target else ""
    return f"🔗 {name}{arrow}{_marks(module.visible, module.uservisible, module.availability)}"


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
            branch.add(f"🔗 {escape(child.name)} → {escape(child.url)}")


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
            if module.modname == "url":
                branch.add(_url_label(module))
                continue
            module_branch = branch.add(_module_label(module))
            _render_children(module_branch, module.children)
    return root


def _print_tree(tree: Tree) -> None:
    """Baum ohne Breitenbegrenzung drucken, damit lange URLs nicht abgeschnitten werden."""
    scratch = Console(width=1_000_000, height=25, highlight=False, soft_wrap=True)
    width = max(out_console.width, scratch.measure(tree).maximum + 1)
    tree_console = Console(
        file=sys.stdout,
        width=width,
        height=out_console.height or 25,
        highlight=False,
        soft_wrap=True,
    )
    tree_console.print(tree)


def print_contents(result: CourseContentsResult) -> None:
    _print_tree(_contents_tree(result))
    out_console.print(f"[dim]{result.timestamp}[/dim]")
