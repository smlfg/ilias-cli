"""Fassade der Kernbibliothek: Instanz auflösen, Backend wählen, Operationen ausführen.

Die CLI ruft nur diese Funktionen auf und formatiert die Rückgabewerte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .auth import prompt_credentials
from .backends import get_backend
from .config import Instance, load_instance
from .errors import CourseAmbiguousError, CourseNotFoundError
from .models import (
    Course,
    CoursesResult,
    Credentials,
    LoginResult,
    LogoutResult,
    LsResult,
    ModuleInfo,
    SectionInfo,
    StatusResult,
)

if TYPE_CHECKING:  # vermeidet einen Import-Zyklus (backends -> models -> ...)
    from .backends.base import Backend


@dataclass(frozen=True)
class Service:
    instance: Instance
    backend: Backend

    @property
    def key(self) -> str:
        return self.instance.key

    def login(self, credentials: Credentials | None = None) -> LoginResult:
        """Anmelden. Ohne `credentials` wird verdeckt nach Benutzername/Passwort gefragt."""
        creds = credentials if credentials is not None else prompt_credentials()
        return self.backend.login(creds)

    def status(self) -> StatusResult:
        return self.backend.status()

    def logout(self) -> LogoutResult:
        return self.backend.logout()

    def courses(self) -> CoursesResult:
        """Eigene Kurse des eingeloggten Benutzers (F2, bereits sortiert)."""
        found = self.backend.courses()
        return CoursesResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            courses=tuple(found),
        )

    def ls(self, query: str, depth: int | None = None) -> LsResult:
        """Kursinhalt als Baum (F3): Kurs per Id/Substring auflösen, dann laden.

        `depth`: 1 = nur Abschnitte, 2 = + Bausteine, 3 = + Dateien/erste
        Ordnerebene, jede weitere Stufe eine Unterordnerebene mehr.
        None = unbegrenzt.
        """
        found = self.backend.courses()
        course = resolve_course(query, found)
        sections = self.backend.course_contents(course.id)
        if depth is not None:
            sections = _prune_sections(sections, depth)
        return LsResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            course=course,
            depth=depth,
            sections=tuple(sections),
        )


def resolve_course(query: str, found: list[Course]) -> Course:
    """Kurs per numerischer Id oder case-insensitivem Teilstring finden.

    Ein exakter (case-insensitiver) shortname/fullname-Treffer schlägt
    Teilstring-Treffer. Kein Treffer -> CourseNotFoundError, mehrere Treffer
    -> CourseAmbiguousError (mit Kandidatenliste).
    """
    text = (query or "").strip()
    if not text:
        raise CourseNotFoundError(
            "Kein Kurs angegeben.",
            hint="Verfügbare Kurse mit `ilias courses` anzeigen.",
        )
    if text.isdigit():
        wanted = int(text)
        for course in found:
            if course.id == wanted:
                return course
        raise CourseNotFoundError(
            f"Kurs mit der Id {wanted} nicht gefunden.",
            hint="Verfügbare Kurse mit `ilias courses` anzeigen.",
        )
    folded = text.casefold()
    exact = [
        c
        for c in found
        if c.shortname.casefold() == folded or c.fullname.casefold() == folded
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise _ambiguous(text, exact)
    partial = [
        c
        for c in found
        if folded in c.shortname.casefold() or folded in c.fullname.casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise CourseNotFoundError(
            f"Kein Kurs passt zu {text!r}.",
            hint="Verfügbare Kurse mit `ilias courses` anzeigen.",
        )
    raise _ambiguous(text, partial)


def _ambiguous(text: str, matches: list[Course]) -> CourseAmbiguousError:
    candidates = [c.candidate_dict() for c in matches]
    lines = ", ".join(f"{c['id']} ({c['shortname']}: {c['fullname']})" for c in candidates)
    return CourseAmbiguousError(
        f"Mehrere Kurse passen zu {text!r}: {lines}.",
        hint="Bitte per Id oder exaktem Kurznamen wählen, z. B. `ilias ls <id>`.",
        candidates=candidates,
    )


def _prune_sections(sections: list[SectionInfo], depth: int) -> list[SectionInfo]:
    """Baum auf `depth` Stufen beschneiden (1 = nur Abschnitte)."""
    from .models import FolderChild

    if depth <= 0:
        return []
    if depth == 1:
        return [
            SectionInfo(
                id=s.id,
                number=s.number,
                name=s.name,
                visible=s.visible,
                uservisible=s.uservisible,
                modules=(),
            )
            for s in sections
        ]
    pruned: list[SectionInfo] = []
    for section in sections:
        modules: list[ModuleInfo] = []
        for module in section.modules:
            if depth == 2:
                children: tuple = ()
            else:
                children = _prune_children(module.children, current_level=3, max_depth=depth)
            modules.append(
                ModuleInfo(
                    id=module.id,
                    name=module.name,
                    modname=module.modname,
                    url=module.url,
                    visible=module.visible,
                    uservisible=module.uservisible,
                    availability=module.availability,
                    children=children,
                )
            )
        pruned.append(
            SectionInfo(
                id=section.id,
                number=section.number,
                name=section.name,
                visible=section.visible,
                uservisible=section.uservisible,
                modules=tuple(modules),
            )
        )
    return pruned


def _prune_children(children: tuple, *, current_level: int, max_depth: int) -> tuple:
    """Kinder auf `max_depth` beschneiden; Ordnerkinder liegen eine Stufe tiefer."""
    from .models import FolderChild

    if current_level > max_depth:
        return ()
    kept: list = []
    for child in children:
        if isinstance(child, FolderChild):
            sub = _prune_children(child.children, current_level=current_level + 1, max_depth=max_depth)
            kept.append(
                FolderChild(name=child.name, path=child.path, children=sub)
            )
        else:
            kept.append(child)
    return tuple(kept)


def open_service(instance_key: str | None = None, config: dict | None = None) -> Service:
    instance = load_instance(instance_key, config)
    return Service(instance=instance, backend=get_backend(instance))
