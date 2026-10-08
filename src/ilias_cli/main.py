"""Dünne CLI-Hülle: Typer-Kommandos, JSON-Ausgabe, Exit-Codes (INTERFACE.md).

Keine Logik hier: Auflösen der Instanz, Login/Status/Logout und die Fehler->Exit-Code-
Abbildung kommen aus `ilias_core`.
"""

from __future__ import annotations

import json
import os
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
from ilias_core.models import (
    CoursesResult,
    LoginResult,
    LogoutResult,
    LsResult,
    StatusResult,
)

app = typer.Typer(
    help="ilias-cli – Login/Status/Logout für ILIAS- und Moodle-Instanzen (Hochschulen).",
    no_args_is_help=True,
)

def _console_size() -> tuple[int, int]:
    """Explizite Konsolengröße für Rich.

    Hintergrund: Meldet Rich `is_dumb_terminal` (TERM=dumb plus Ausgabe, die
    es für ein Terminal hält – z. B. durch FORCE_COLOR=0 in der Umgebung),
    meldet `Console.size` stur 80×25 und ignoriert dabei COLUMNS sowie eine
    per `width=` gesetzte Breite. Lange Baumzeilen würden dann umbrochen
    (Verfügbarkeitstexte zerreißen über Folgezeilen) oder abgeschnitten.
    Sind Breite *und* Höhe gesetzt, meldet `size` diese direkt zurück und
    jede Zeile bleibt ganz (Ausgabe wird nie still beschnitten).
    """

    def _env_int(name: str, minimum: int, fallback: int) -> int:
        try:
            value = int(os.environ.get(name, "") or 0)
        except ValueError:
            return fallback
        return value if value >= minimum else fallback

    return (_env_int("COLUMNS", 80, 200), _env_int("LINES", 10, 1000))


_CONSOLE_WIDTH, _CONSOLE_HEIGHT = _console_size()
err_console = Console(stderr=True, highlight=False, width=_CONSOLE_WIDTH, height=_CONSOLE_HEIGHT)
out_console = Console(highlight=False, width=_CONSOLE_WIDTH, height=_CONSOLE_HEIGHT)

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
        candidates=list(candidates) if candidates else None,
    )
    if json_output:
        _dump(result.to_json_dict())
    err_console.print(f"[bold red]Fehler:[/bold red] {escape(exc.message)}")
    if candidates:
        for cand in candidates:
            err_console.print(
                f"  [dim]{escape(str(cand.get('id')))}[/dim] "
                f"{escape(str(cand.get('shortname')))} – {escape(str(cand.get('fullname')))}"
            )
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


# ---------------------------------------------------------------- F2/F3: Kurse und Inhalte (Moodle)

_MOD_ICONS: dict[str, str] = {
    "folder": "📁",
    "resource": "📄",
    "file": "📄",
    "assign": "📝",
    "forum": "💬",
    "url": "🔗",
    "quiz": "❓",
    "page": "📃",
    "label": "🏷️",
    "choice": "🗳️",
    "lti": "🔌",
}

_MOD_LABELS: dict[str, str] = {
    "folder": "Ordner",
    "resource": "Datei",
    "assign": "Aufgabe",
    "forum": "Forum",
    "url": "Link",
    "quiz": "Test",
    "page": "Seite",
    "label": "Text",
    "choice": "Abstimmung",
    "lti": "Tool",
}


def _format_size(size: int | None) -> str:
    if size is None:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        kb = size / 1024
        return f"{kb:.0f} KB" if kb >= 100 else f"{kb:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _visibility_suffix(*, visible: bool, uservisible: bool, availability: str | None = None) -> str:
    parts: list[str] = []
    if not uservisible:
        parts.append("[gesperrt]")
    if not visible:
        parts.append("[verborgen]")
    if availability and not uservisible:
        parts.append(f"({availability})")
    return " " + " ".join(parts) if parts else ""


def _courses_table(result: CoursesResult) -> Table:
    table = Table("ID", "Kurzname", "Name", "Semester")
    for course in result.courses:
        name = course.fullname if course.visible else f"{course.fullname} [verborgen]"
        table.add_row(
            str(course.id),
            escape(course.shortname),
            escape(name),
            escape(course.semester or "–"),
        )
    return table


def _build_ls_tree(result: LsResult) -> Tree:
    from ilias_core.models import FileChild, FolderChild, UrlChild

    course = result.course
    title = escape(course.fullname) if course else "Kurs"
    root = Tree(f"📚 {title}")
    for section in result.sections:
        sec_name = section.name.strip() or f"Abschnitt {section.number}"
        sec_suffix = _visibility_suffix(visible=section.visible, uservisible=section.uservisible)
        # Leere Abschnitte ohne Namen in der Menschenansicht überspringen (JSON behält sie).
        if not section.modules and (not section.name.strip()):
            continue
        sec_node = root.add(f"§ {escape(sec_name)}{escape(sec_suffix)}")
        for module in section.modules:
            icon = _MOD_ICONS.get(module.modname, "📦")
            kind = _MOD_LABELS.get(module.modname, module.modname or "Eintrag")
            mod_suffix = _visibility_suffix(
                visible=module.visible,
                uservisible=module.uservisible,
                availability=module.availability,
            )
            mod_node = sec_node.add(f"{icon} {escape(module.name)} [{escape(kind)}]{escape(mod_suffix)}")
            _add_children(mod_node, module.children)
    return root


def _add_children(node: Tree, children: tuple) -> None:
    from ilias_core.models import FileChild, FolderChild, UrlChild

    for child in children:
        if isinstance(child, FolderChild):
            sub = node.add(f"📁 {escape(child.name)} [Ordner]")
            _add_children(sub, child.children)
        elif isinstance(child, FileChild):
            size = _format_size(child.size)
            extra = f" ({size})" if size else ""
            node.add(f"📄 {escape(child.name)}{escape(extra)}")
        elif isinstance(child, UrlChild):
            node.add(f"🔗 {escape(child.name)} → {escape(child.url or '')}")
        else:  # pragma: no cover - unbekannter Kindknoten
            node.add(f"📦 {escape(str(getattr(child, 'name', child)))}")


@app.command(name="courses")
def courses(
    instance: str | None = _instance_option(),
    json_output: bool = _json_option(),
) -> None:
    """Eigene Kurse auflisten (Moodle; Titel, Kurzname, Semester)."""
    result: CoursesResult = _run("courses", json_output, instance, lambda service: service.courses())
    if json_output:
        _dump(result.to_json_dict())
        return
    if not result.courses:
        out_console.print("Keine Kurse gefunden.")
        return
    out_console.print(_courses_table(result))
    out_console.print(f"[dim]{len(result.courses)} Kurse · {result.timestamp}[/dim]")


@app.command(name="ls")
def ls(
    kurs: str = typer.Argument(..., help="Kurs-Id oder Teil von Kurzname/Name (z. B. 'mathe')."),
    instance: str | None = _instance_option(),
    depth: int | None = typer.Option(
        None, "--depth", "-d", help="Tiefe: 1 = nur Abschnitte, 2 = + Bausteine, 3 = + Dateien."
    ),
    json_output: bool = _json_option(),
) -> None:
    """Inhalt eines Kurses als Baum anzeigen (Moodle)."""
    if depth is not None and depth < 1:
        raise typer.BadParameter("--depth muss mindestens 1 sein.")
    result: LsResult = _run("ls", json_output, instance, lambda service: service.ls(kurs, depth))
    if json_output:
        _dump(result.to_json_dict())
        return
    out_console.print(_build_ls_tree(result))
    out_console.print(f"[dim]{result.timestamp}[/dim]")


def main_entrypoint() -> None:  # pragma: no cover - Einstieg über Konsolen-Skript
    app()


if __name__ == "__main__":  # pragma: no cover
    main_entrypoint()
