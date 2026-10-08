"""F2/F3: Kurslogik ohne HTTP - Semester, Sortierung, Kursauflösung, Baum, Tiefe.

Alles hier ist eine reine Funktion über die Dataclasses aus `models.py`:
aufrufbar ohne Server, ohne Session und ohne CLI.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from .errors import CourseAmbiguousError, CourseNotFoundError
from .models import ContentNode, Course, FileNode, FolderNode, ModuleNode, SectionNode
from .timeutil import semester_year

ID_HINT = "Kurs-ID (Zahl) oder ein Stück aus Kurzname/Titel angeben, z. B. `ilias ls 51234`."


# --------------------------------------------------------------------- Sortierung
def course_sort_key(course: Course) -> tuple[bool, int, str, str]:
    """Neuestes Semester zuerst, unbekanntes Semester zuletzt, dann Titel/Kurzname."""
    return (
        course.semester is None,
        -semester_year(course.semester),
        course.fullname.casefold(),
        course.shortname.casefold(),
    )


def sort_courses(courses: Iterable[Course]) -> tuple[Course, ...]:
    return tuple(sorted(courses, key=course_sort_key))


# --------------------------------------------------------------------- Kurs auflösen
def _candidate(course: Course) -> dict[str, object]:
    return {"id": course.id, "shortname": course.shortname, "fullname": course.fullname}


def _describe(courses: Sequence[Course]) -> str:
    return ", ".join(f"{c.id} ({c.shortname}, {c.fullname})" for c in courses)


def _ambiguous(query: str, matches: Sequence[Course]) -> CourseAmbiguousError:
    return CourseAmbiguousError(
        f"Mehrere Kurse passen zu {query!r}: {_describe(matches)}.",
        hint=f"Mehrdeutig - bitte genauer angeben ({ID_HINT}).",
        details={"candidates": [_candidate(course) for course in matches]},
    )


def resolve_course(courses: Sequence[Course], query: str) -> Course:
    """`<kurs>` auflösen: Kurs-ID, exakter Kurzname/Titel oder Teilstring.

    Reihenfolge: numerische Kurs-ID, exakter Kurzname, exakter Titel,
    Teilstring (case-insensit). Genau ein Treffer wird verwendet, mehrere
    ergeben `course_ambiguous` mit den Kandidaten, keiner `course_not_found`.
    """
    needle = (query or "").strip()
    if not needle:
        raise CourseNotFoundError("Kein Kurs angegeben.", hint=ID_HINT)

    if needle.isdigit():
        wanted = int(needle)
        for course in courses:
            if course.id == wanted:
                return course

    folded = needle.casefold()
    for attribute in ("shortname", "fullname"):
        exact = [c for c in courses if getattr(c, attribute).casefold() == folded]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise _ambiguous(needle, exact)

    matches = [c for c in courses if folded in c.shortname.casefold() or folded in c.fullname.casefold()]
    if not matches:
        raise CourseNotFoundError(
            f"Kein Kurs passt zu {needle!r}.",
            hint=f"Gesucht wurde in {len(courses)} Kursen. {ID_HINT}",
        )
    if len(matches) == 1:
        return matches[0]
    raise _ambiguous(needle, matches)


# --------------------------------------------------------------------- Ordnerbaum
class _Dir:
    """Arbeitsknoten beim Aufbau der Ordnerstruktur aus `filepath`."""

    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.path = path
        self.subdirs: dict[str, _Dir] = {}
        self.files: list[FileNode] = []

    def subdir(self, name: str) -> _Dir:
        existing = self.subdirs.get(name)
        if existing is None:
            existing = _Dir(name, f"{self.path}{name}/")
            self.subdirs[name] = existing
        return existing

    def nodes(self) -> tuple[ContentNode, ...]:
        folders = [_dir_node(sub) for sub in self.subdirs.values()]
        return tuple(folders + list(self.files))


def _dir_node(directory: _Dir) -> FolderNode:
    return FolderNode(name=directory.name, path=directory.path, children=directory.nodes())


def nest_files(files: Sequence[FileNode]) -> tuple[ContentNode, ...]:
    """Dateien eines `folder`-Moduls nach `filepath` zu Unterordnern verschachteln.

    `"/"` -> Dateien direkt im Modul, `"/Blatt 1/Lösungen/"` -> Ordner `Blatt 1`
    mit Unterordner `Lösungen`. Reihenfolge der Ordner und Dateien folgt der
    Antwort des Servers.
    """
    root = _Dir("", "/")
    for entry in files:
        parts = [part for part in entry.path.split("/") if part]
        node = root
        for part in parts:
            node = node.subdir(part)
        node.files.append(entry)
    return root.nodes()


# --------------------------------------------------------------------- Tiefe
def _prune_nodes(nodes: Sequence[ContentNode], depth: int, level: int) -> tuple[ContentNode, ...]:
    if level > depth:
        return ()
    pruned: list[ContentNode] = []
    for node in nodes:
        if isinstance(node, FolderNode):
            pruned.append(replace(node, children=_prune_nodes(node.children, depth, level + 1)))
        else:
            pruned.append(node)
    return tuple(pruned)


def _prune_module(module: ModuleNode, depth: int) -> ModuleNode:
    """Modulebene 2, Dateien/Ordner Ebene 3, jeder weitere Unterordner eine Ebene."""
    if depth < 3:
        return replace(module, children=())
    return replace(module, children=_prune_nodes(module.children, depth, 3))


def apply_depth(sections: Sequence[SectionNode], depth: int | None) -> tuple[SectionNode, ...]:
    """`--depth`: 1 = nur Abschnitte, 2 = + Module, 3 = + Dateien/erste Ordnerebene.

    `None` (Vorgabe) = unbegrenzt. Die Kürzung verändert die Daten nur in der
    Darstellung - die JSON-Ausgabe enthält genau diese (gekürzte) Struktur.
    """
    if depth is None:
        return tuple(sections)
    if depth < 1:
        raise ValueError("depth >= 1")
    return tuple(
        replace(
            section,
            modules=tuple(_prune_module(module, depth) for module in section.modules) if depth >= 2 else (),
        )
        for section in sections
    )
