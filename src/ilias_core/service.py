"""Fassade der Kernbibliothek: Instanz auflösen, Backend wählen, Operationen ausführen.

Die CLI ruft nur diese Funktionen auf und formatiert die Rückgabewerte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .auth import prompt_credentials
from .backends import get_backend
from .config import Instance, load_instance
from .errors import CoreError
from .models import (
    Course,
    CourseContentsResult,
    CourseFolder,
    CourseModule,
    CourseSection,
    CoursesResult,
    Credentials,
    LoginResult,
    LogoutResult,
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
        """Eigene Kurse auflisten (F2)."""
        return self.backend.courses()

    def ls(self, query: str, depth: int | None = None) -> CourseContentsResult:
        """Inhalt eines Kurses als Baum (F3).
        
        `query` ist entweder eine numerische Kurs-ID oder ein Substring von fullname/shortname.
        Exakte Matches (case-insensitive) auf shortname oder fullname haben Vorrang.
        """
        # Zuerst alle Kurse holen um aufzulösen
        courses_result = self.backend.courses()
        courses = list(courses_result.courses)
        
        # Kurs auflösen
        course = self._resolve_course(courses, query)
        
        # Kursinhalt abrufen
        result = self.backend.course_contents(course.id)
        
        # Kurs-Info im Ergebnis aktualisieren
        course_info = {"id": course.id, "fullname": course.fullname, "shortname": course.shortname}
        
        # Tiefe anwenden (Filterung der Sections/Modules/Files)
        if depth is not None and depth < 1:
            raise CoreError(
                "Tiefe (--depth) muss >= 1 sein.",
                hint="Erlaubte Werte: 1 (nur Abschnitte), 2 (+ Module), 3 (+ Dateien/1. Ordnerebene), ...",
            )
        
        filtered_sections = self._apply_depth(result.sections, depth) if depth is not None else result.sections
        
        return CourseContentsResult(
            instance=result.instance,
            lms=result.lms,
            course=course_info,
            depth=depth,
            sections=filtered_sections,
            timestamp=result.timestamp,
        )

    def _resolve_course(self, courses: list[Course], query: str) -> Course:
        """Löst einen Kurs aus der Liste auf: ID, exakter shortname/fullname, Substring."""
        # 1. Numerische ID
        if query.isdigit():
            course_id = int(query)
            for c in courses:
                if c.id == course_id:
                    return c
            raise CoreError(
                f"Kurs mit ID {course_id} nicht gefunden.",
                hint="Verfügbare Kurse mit `ilias courses` anzeigen.",
            )
        
        # 2. Exakte Matches (case-insensitive) auf shortname oder fullname
        query_lower = query.lower()
        exact_matches = []
        for c in courses:
            if c.shortname.lower() == query_lower or c.fullname.lower() == query_lower:
                exact_matches.append(c)
        
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            # Mehrere exakte Matches (sollte selten sein) -> als mehrdeutig behandeln
            self._raise_ambiguous(exact_matches)
        
        # 3. Substring-Matches (case-insensitive) auf shortname oder fullname
        substring_matches = []
        for c in courses:
            if query_lower in c.shortname.lower() or query_lower in c.fullname.lower():
                substring_matches.append(c)
        
        if len(substring_matches) == 1:
            return substring_matches[0]
        if len(substring_matches) == 0:
            raise CoreError(
                f"Kein Kurs gefunden, der '{query}' enthält.",
                hint="Verfügbare Kurse mit `ilias courses` anzeigen.",
            )
        
        # Mehrere Substring-Matches -> mehrdeutig
        self._raise_ambiguous(substring_matches)

    def _raise_ambiguous(self, candidates: list[Course]) -> None:
        """Wirft einen Fehler für mehrdeutige Kurs-Auflösung."""
        candidates_info = [
            {"id": c.id, "shortname": c.shortname, "fullname": c.fullname}
            for c in candidates
        ]
        lines = [f"  {c['id']}: {c['shortname']} – {c['fullname']}" for c in candidates_info]
        msg = "Mehrere Kurse passen zur Anfrage:\n" + "\n".join(lines)
        # Wir nutzen einen CoreError mit speziellem code und fügen candidates als Attribut hinzu
        exc = CoreError(msg, hint="Genauere Angabe (z. B. Kurs-ID oder exakter Kurzname) verwenden.")
        exc.exit_code = 1
        exc.code = "course_ambiguous"
        # candidates für JSON-Output speichern
        exc.candidates = candidates_info  # type: ignore[attr-defined]
        raise exc

    def _apply_depth(self, sections: tuple, depth: int) -> tuple:
        """Wendet die Tiefenbegrenzung auf die Kursstruktur an.
        
        depth=1: nur Abschnitte
        depth=2: + Module
        depth=3: + Dateien/erste Ordnerebene
        depth=N: jede weitere Ebene = eine Unterordnerebene mehr
        """
        if depth <= 0:
            return ()
        
        filtered_sections = []
        for section in sections:
            if depth == 1:
                # Nur Abschnitte, keine Module
                filtered_section = CourseSection(
                    id=section.id,
                    number=section.number,
                    name=section.name,
                    visible=section.visible,
                    uservisible=section.uservisible,
                    modules=(),
                )
                filtered_sections.append(filtered_section)
            else:
                # Module filtern
                filtered_modules = []
                for module in section.modules:
                    if depth == 2:
                        # Module ohne Kinder
                        filtered_module = CourseModule(
                            id=module.id,
                            name=module.name,
                            modname=module.modname,
                            url=module.url,
                            visible=module.visible,
                            uservisible=module.uservisible,
                            availability=module.availability,
                            children=(),
                        )
                        filtered_modules.append(filtered_module)
                    else:
                        # Tiefe >= 3: Kinder mit Rekursion filtern
                        filtered_children = self._filter_children(module.children, depth - 2)
                        filtered_module = CourseModule(
                            id=module.id,
                            name=module.name,
                            modname=module.modname,
                            url=module.url,
                            visible=module.visible,
                            uservisible=module.uservisible,
                            availability=module.availability,
                            children=filtered_children,
                        )
                        filtered_modules.append(filtered_module)
                
                filtered_section = CourseSection(
                    id=section.id,
                    number=section.number,
                    name=section.name,
                    visible=section.visible,
                    uservisible=section.uservisible,
                    modules=tuple(filtered_modules),
                )
                filtered_sections.append(filtered_section)
        
        return tuple(filtered_sections)

    def _filter_children(self, children: tuple, remaining_depth: int) -> tuple:
        """Filtert Kinder rekursiv basierend auf verbleibender Tiefe.
        
        remaining_depth=1: nur erste Ebene der Kinder (Dateien/Ordner direkt im Modul)
        remaining_depth=2: + Unterordner 1. Ebene
        etc.
        """
        if remaining_depth <= 0:
            return ()
        
        filtered = []
        for child in children:
            if hasattr(child, 'children') and child.children:
                # Folder mit Kindern
                if remaining_depth == 1:
                    # Nur dieser Ordner, keine Kinder
                    filtered_child = CourseFolder(
                        name=child.name,
                        path=child.path,
                        children=(),
                    )
                    filtered.append(filtered_child)
                else:
                    # Rekursiv filtern
                    filtered_children = self._filter_children(child.children, remaining_depth - 1)
                    filtered_child = CourseFolder(
                        name=child.name,
                        path=child.path,
                        children=filtered_children,
                    )
                    filtered.append(filtered_child)
            else:
                # File oder URL (Blatt)
                filtered.append(child)
        
        return tuple(filtered)


def open_service(instance_key: str | None = None, config: dict | None = None) -> Service:
    instance = load_instance(instance_key, config)
    return Service(instance=instance, backend=get_backend(instance))
