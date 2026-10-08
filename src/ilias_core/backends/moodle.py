"""Moodle-Backend: Login/Status/Logout über den offiziellen Moodle-Mobile-Webservice.

Geprüft am 08.10.2026 (siehe real-fixtures/NOTES.md, Abschnitt "HS Mannheim Moodle"):
`enablewebservices = 1`, `enablemobilewebservice = 1`, `typeoflogin = 1`
(Benutzername/Passwort), keine Identity Provider, kein 2FA.

Ablauf:
1. POST {base}/login/token.php            -> username, password, service=moodle_mobile_app
   Erfolg: {"token": ...}  ·  Fehler: {"error": ..., "errorcode": "invalidlogin"}
2. Verifikation: POST {base}/webservice/rest/server.php
   wstoken, wsfunction=core_webservice_get_site_info, moodlewsrestformat=json
   -> {"sitename", "username", "fullname", "userid", ...}  ·  {"exception": ..., "errorcode": "invalidtoken"}
3. Erst nach erfolgreicher Verifikation wird der Token gespeichert.

Erweiterte Operationen (F2/F3):
- courses(): Eigenen Kursliste via core_enrol_get_users_courses
- course_contents(): Kursinhalte als Baum via core_course_get_contents
- course_resolution(): Auflösen eines Kursnamens/ids (substring, exakte Übereinstimmung, Ambiguität)
"""

from __future__ import annotations

import re
import time
from typing import Any

from ..errors import (
    AuthError,
    NetworkError,
    NotLoggedInError,
    ParseError,
    SessionExpiredError,
)
from ..http import HttpClient, json_body
from ..models import (
    Credentials,
    Course,
    CourseSection,
    LoginResult,
    LogoutResult,
    SiteInfo,
    StatusResult,
)
from ..secrets import REDACTED
from ..session import SessionStore
from .base import Backend

TOKEN_PATH = "/login/token.php"
REST_PATH = "/webservice/rest/server.php"
SERVICE = "moodle_mobile_app"
SITE_INFO_FUNCTION = "core_webservice_get_site_info"
REST_FORMAT = "json"

# Fehlercodes, die einen abgelehnten Login bedeuten (Moodle: login/token.php)
_AUTH_ERROR_CODES = {"invalidlogin", "invaliduser", "invalidaccount"}
_DENIED_ERROR_CODES = {"accessexception", "nopermission", "nopermtostore", "forbidden"}
# N2: Statusprüfung ist idempotent und darf einmal wiederholt werden
_SITE_INFO_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 0.5


def scrub(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Entfernt Passwort/Token aus Servertexten (A1/A4)."""
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, REDACTED)
    return text


def _strip_availabilityinfo(text: str | None) -> str | None:
    """Stripped HTML from availabilityinfo if present."""
    if not text:
        return None
    # Entferne <div>...</div> Blöcke
    cleaned = re.sub(r'<div[^>]*>(.*?)</div>', r'\1', text, flags=re.DOTALL)
    # Entferne verbleibende HTML-Tags
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    return cleaned.strip() if cleaned.strip() else None


class MoodleBackend(Backend):
    name = "moodle"
    supports_login = True

    def __init__(self, instance) -> None:
        super().__init__(instance)
        self.store = SessionStore(instance.key, instance.lms, instance.base_url)

    # -- Operationen ----------------------------------------------------

    def login(self, credentials: Credentials) -> LoginResult:
        with HttpClient(self.base_url) as client:
            token = self._request_token(client, credentials)
            info = self._site_info(client, token, label="Verifikation des Webservice")
        # erst nach erfolgreicher Verifikation wird der Token gespeichert
        self.store.save(token, username=info.username or credentials.username)
        return LoginResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            base_url=self.base_url,
            username=info.username or credentials.username,
            fullname=info.fullname,
            sitename=info.sitename,
            userid=info.userid,
            verified=True,
            token_stored=True,
        )

    def status(self) -> StatusResult:
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        try:
            with HttpClient(self.base_url) as client:
                info = self._site_info(client, session.token, label="Statusprüfung")
        except SessionExpiredError:
            self.store.delete()
            raise
        return StatusResult(
            instance=self.instance.key,
            lms=self.instance.lms,
            base_url=self.base_url,
            username=info.username,
            fullname=info.fullname,
            sitename=info.sitename,
            userid=info.userid,
            logged_in=True,
        )

    def logout(self) -> LogoutResult:
        removed = self.store.delete()
        return LogoutResult(instance=self.instance.key, lms=self.instance.lms, token_removed=removed)

    # -- Moodle-spezifische Operationen --------------------------------

    def courses(self) -> list[Course]:
        """Eigene Kurse auflisten via core_enrol_get_users_courses.

        Flow: stored token → core_webservice_get_site_info (gets userid)
              → core_enrol_get_users_courses with userid.
        """
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        token = session.token

        # Site-Info holen, um userid zu erhalten
        payload = {
            "wstoken": token,
            "wsfunction": SITE_INFO_FUNCTION,
            "moodlewsrestformat": REST_FORMAT,
        }
        info = self._request_site_info(token=token, label="Site-Info")
        userid = info.userid

        # Jetzt Kurse abfragen
        payload = {
            "wstoken": token,
            "wsfunction": "core_enrol_get_users_courses",
            "moodlewsrestformat": REST_FORMAT,
            "userid": userid,
        }
        data = self._request(REST_PATH, payload, label="Kurse auflisten")
        courses = self._parse_courses(data)
        return courses

    def course_contents(self, course_id: int) -> list[CourseSection]:
        """Inhalt eines Kurses als Abschnitt-Liste holen via core_course_get_contents.

        Flow: courseid → core_course_get_contents
        """
        session = self.store.load()
        if session is None:
            raise NotLoggedInError(
                f"Keine gespeicherte Session für {self.instance.key}.",
                hint=f"Erst `ilias login --instance {self.instance.key}` aufrufen.",
            )
        token = session.token

        payload = {
            "wstoken": token,
            "wsfunction": "core_course_get_contents",
            "moodlewsrestformat": REST_FORMAT,
            "courseid": course_id,
        }
        data = self._request(REST_PATH, payload, label="Kursinhalte")
        sections = self._parse_sections(data)
        return sections

    # -- Course resolution -------------------------------------------------------

def resolve_course(query: str, courses: list[Course]) -> tuple[Course | None, list[Course] | None, str | None]:
    """Resolve a course query to a single Course.

    Returns (course, candidates, error_code):
      - course: the resolved Course if exactly one match, else None
      - candidates: list of candidate Courses if ambiguous, else []
      - error_code: None if ok, "course_not_found" if no match, "course_ambiguous" if multiple
    """
    if not courses:
        return None, [], "course_not_found"

    query_lower = query.lower().strip()

    # Try numeric ID match first
    if query_lower.isdigit():
        course_id = int(query_lower)
        for c in courses:
            if c.id == course_id:
                return c, [], None

    # Find exact matches (case-insensitive shortname or fullname)
    exact_matches: list[Course] = []
    substring_matches: list[Course] = []

    for c in courses:
        # Exact match: case-insensitive shortname or fullname
        if c.shortname.lower() == query_lower or c.fullname.lower() == query_lower:
            exact_matches.append(c)
        # Substring match: query is substring of shortname or fullname
        elif query_lower in c.shortname.lower() or query_lower in c.fullname.lower():
            substring_matches.append(c)

    # Exact matches win over substring matches
    all_exact = exact_matches + [c for c in substring_matches if c not in exact_matches]

    if len(all_exact) == 1:
        return all_exact[0], [], None

    # Collect unique candidates (dedup by id)
    seen_ids = set()
    candidates: list[Course] = []
    for c in all_exact:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            candidates.append(c)

    if len(candidates) == 1:
        return candidates[0], [], None

    if len(candidates) > 1:
        return None, candidates, "course_ambiguous"

    # No match at all - check if we had substring matches only
    if substring_matches:
        seen_ids = set()
        candidates = []
        for c in substring_matches:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                candidates.append(c)
        if len(candidates) == 1:
            return candidates[0], [], None
        if len(candidates) > 1:
            return None, candidates, "course_ambiguous"

    return None, [], "course_not_found"


# -- Tree building helpers ---------------------------------------------------


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', '', text)
    return cleaned.strip()


def _strip_html_brief(text: str, max_chars: int = 60) -> str:
    """Strip HTML and truncate to max characters."""
    plain = _strip_html_tags(text)
    return plain[:max_chars]


def _format_availability(uservisible: bool | None, availabilityinfo: str | None) -> str | None:
    """Format availability info for display.

    Returns None if visible, or a marked string if not visible.
    """
    if uservisible:
        return None
    if availabilityinfo:
        stripped = _strip_availabilityinfo(availabilityinfo)
        if stripped:
            return f"[gesperrt] {stripped}"
    return "[gesperrt]"


def _build_folder_tree(modules: list[dict[str, Any]], depth: int | None, current_depth: int = 0) -> list[dict[str, Any]]:
    """Build a nested folder tree from modules, respecting depth limit.

    Folders (modname == "folder") with filepath become nested sub-folder nodes.
    Files and other modules are leaf nodes.
    """
    if current_depth >= depth and depth is not None:
        # At the depth limit, don't descend further
        # Return only leaf modules at this level
        result: list[dict[str, Any]] = []
        for mod in modules:
            modname = mod.get("modname", "")
            if modname == "folder":
                continue  # Skip folders at depth limit
            result.append(_module_to_leaf(mod))
        return result

    result: list[dict[str, Any]] = []
    for mod in modules:
        modname = mod.get("modname", "")

        if modname == "folder":
            # Build nested folder structure from filepath
            filepath = mod.get("contents", [{}])[0].get("filepath", "") if mod.get("contents") else ""
            # Parse the filepath into segments
            # filepath examples: "/", "/Blatt 1/", "/Blatt 1/Lösungen/"
            children = _parse_filepath(filepath, depth, current_depth + 1)
            mod_name = mod.get("name", "")
            if children or current_depth == 0:
                result.append({
                    "type": "folder",
                    "name": mod_name,
                    "path": filepath,
                    "children": children,
                })
            # Don't also add the files as separate leaves if they're in the folder
            continue

        # Resource modules (file, url, etc.) and other modules
        result.append(_module_to_leaf(mod, depth, current_depth + 1))

    return result


def _parse_filepath(filepath: str, depth: int | None, current_depth: int) -> list[dict[str, Any]]:
    """Parse a filepath like "/Blatt 1/" or "/Blatt 1/Lösungen/" into nested folder nodes."""
    if not filepath:
        return []

    # Remove trailing slash for processing
    path = filepath.rstrip("/")
    if not path:
        # Empty filepath, just add as a file at current level
        return []

    # Split by "/" to get segments
    segments = [s.strip() for s in path.split("/") if s.strip()]

    if not segments:
        return []

    # Build nested structure
    result: list[dict[str, Any]] = []
    node: dict[str, Any] = {"type": "folder", "name": segments[0], "children": []}
    current = node

    for segment in segments[1:]:
        child = {"type": "folder", "name": segment, "children": []}
        current["children"].append(child)
        current = child

    # If we're at the right depth, add any file children
    # For now, just return the folder structure
    return [node]


def _module_to_leaf(
    mod: dict[str, Any],
    depth: int | None = None,
    current_depth: int = 0,
) -> dict[str, Any]:
    """Convert a module dict to a leaf node dict for the ls tree.

    Handles: folder, url, and other module types (assign, forum, quiz, page, label, etc.)
    """
    modname = mod.get("modname", "")
    name = mod.get("name", "")
    url = mod.get("url", "")
    visible = mod.get("visible", True)
    uservisible = mod.get("uservisible", True)
    availability = mod.get("availability", None)

    # Strip HTML from label module names
    if modname == "label":
        name = _strip_html_brief(name, max_chars=60)

    # Format availability
    avail_str = _format_availability(uservisible, availability)

    # Handle visibility marking
    vis_mark = ""
    if not uservisible and not visible:
        vis_mark = " [gesperrt][verborgen]"
    elif not uservisible:
        vis_mark = " [gesperrt]"
    elif not visible:
        vis_mark = " [verborgen]"

    # Different module types
    if modname == "folder":
        # Folder with contents - the contents are handled separately in _build_folder_tree
        # But if no children, show as folder node
        children_count = mod.get("contentsinfo", {}).get("filescount", 0) if mod.get("contentsinfo") else 0
        disp_name = name + vis_mark if vis_mark else name
        return {
            "id": mod.get("id"),
            "name": disp_name,
            "modname": modname,
            "url": url,
            "visible": visible,
            "uservisible": uservisible,
            "availability": avail_str,
            "type": "folder",
        }

    if modname == "url":
        return {
            "id": mod.get("id"),
            "name": name + vis_mark if vis_mark else name,
            "modname": modname,
            "url": url,
            "visible": visible,
            "uservisible": uservisible,
            "availability": avail_str,
            "type": "url",
        }

    # Resource modules with contents (files, etc.)
    contents = mod.get("contents")
    if contents:
        # Find file(s) in contents
        for content in contents:
            if content.get("type") == "file":
                fname = content.get("filename", "")
                # Strip HTML from filename
                fname = _strip_html_brief(fname, max_chars=60)
                size = content.get("filesize", 0)
                # Format size
                if size > 0:
                    if size >= 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    elif size >= 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size} B"
                else:
                    size_str = ""
                timemodified = content.get("timemodified")
                timemodified_iso = ""
                if timemodified:
                    from datetime import datetime, timezone, timedelta
                    berlin_tz = timezone(timedelta(hours=2))
                    dt = datetime.fromtimestamp(timemodified, tz=berlin_tz)
                    timemodified_iso = dt.strftime("%Y-%m-%dT%H:%M:%S%z")

                return {
                    "id": mod.get("id"),
                    "name": fname + vis_mark if vis_mark else fname,
                    "modname": modname,
                    "url": "",  # Never append token to URL
                    "visible": visible,
                    "uservisible": uservisible,
                    "availability": avail_str,
                    "type": "file",
                    "path": content.get("filepath", ""),
                    "size": size,
                    "mimetype": content.get("mimetype", ""),
                    "timemodified": timemodified_iso,
                }
            elif content.get("type") == "url":
                fu_name = content.get("filename", "")
                fu_name = _strip_html_brief(fu_name, max_chars=60)
                return {
                    "id": mod.get("id"),
                    "name": fu_name + vis_mark if vis_mark else fu_name,
                    "modname": modname,
                    "url": content.get("fileurl", ""),
                    "visible": visible,
                    "uservisible": uservisible,
                    "availability": avail_str,
                    "type": "url",
                }

    # Other modules (assign, forum, quiz, page, label, choice, lti, etc.) - leaf nodes with type label
    # Map modname to type label
    type_labels: dict[str, str] = {
        "assign": "📝 Aufgabe",
        "forum": "💬 Forum",
        "quiz": "❓ Test",
        "page": "📃 Seite",
        "label": "📃 Label",  # Already handled above, but fallback
        "choice": "📋 Wahl",
        "lti": "🔗 LTI",
    }
    type_label = type_labels.get(modname, f"📄 {modname.capitalize()}")

    disp_name = name + vis_mark if vis_mark else name
    return {
        "id": mod.get("id"),
        "name": disp_name,
        "modname": modname,
        "url": url,
        "visible": visible,
        "uservisible": uservisible,
        "availability": avail_str,
        "type": type_label,
    }


def build_ls_tree(
    sections: list[CourseSection],
    depth: int | None = None,
) -> list[dict[str, Any]]:
    """Build an ls tree from parsed CourseSections, respecting depth limit.

    depth: 1 = sections only, 2 = + modules, 3 = + files/first folder level,
           each further level = one more sub-folder level.
    None = unlimited.
    """
    result: list[dict[str, Any]] = []

    for section in sections:
        section_id = section.id
        section_number = section.number
        section_name = section.name
        section_visible = section.visible
        section_uservisible = section.uservisible

        # Format section visibility
        sec_vis_mark = ""
        if not section_uservisible:
            sec_vis_mark = " [gesperrt]"
        elif not section_visible:
            sec_vis_mark = " [verborgen]"

        disp_name = section_name + sec_vis_mark if sec_vis_mark else section_name

        # Build modules for this section
        modules_tree = _build_folder_tree(section.modules, depth, current_depth=1)

        result.append({
            "id": section_id,
            "number": section_number,
            "name": disp_name,
            "visible": section_visible,
            "uservisible": section_uservisible,
            "modules": modules_tree,
        })

    return result

    def _request_site_info(self, token: str, *, label: str) -> SiteInfo:
        """core_webservice_get_site_info anfordern."""
        with HttpClient(self.base_url) as client:
            payload = {
                "wstoken": token,
                "wsfunction": SITE_INFO_FUNCTION,
                "moodlewsrestformat": REST_FORMAT,
            }
            response = client.post_form(REST_PATH, payload, label=label)
            data = json_body(response, label=label)
            self._raise_for_error(data, label=label, secrets=(token,))
            return SiteInfo.from_moodle_json(data)

    def _request(self, path: str, payload: dict[str, str], *, label: str) -> dict[str, Any]:
        """POST an den Moodle-REST-Endpunkt und liefere das JSON-Dict."""
        with HttpClient(self.base_url) as client:
            response = client.post_form(path, payload, label=label)
            data = json_body(response, label=label)
            self._raise_for_error(data, label=label, secrets=(payload.get("wstoken", ""),))
            return data

    def _parse_courses(self, data: dict[str, Any]) -> list[Course]:
        """Parse die Antwort von core_enrol_get_users_courses in Course-Dataclasses.

        Die Moodle-Antwort von core_enrol_get_users_courses ist bereits eine Liste
        von Dicts (eine pro Kurs).
        """
        if not isinstance(data, list):
            raise ParseError(f"Kurse-Antwort ist keine Liste.")

        courses: list[Course] = []
        for raw in data:
            startdate = raw.get("startdate")
            semester = derive_semester(startdate) if startdate else None
            url = f"{self.instance.base_url.rstrip('/')}/course/view.php?id={raw['id']}"

            course = Course(
                id=raw["id"],
                fullname=raw["fullname"],
                shortname=raw["shortname"],
                category=raw.get("category"),
                semester=semester,
                visible=bool(raw.get("visible", 0)),
                startdate=startdate if isinstance(startdate, int) and startdate != 0 else None,
                enddate=raw.get("enddate"),
                url=url,
            )
            courses.append(course)
        return courses

def _parse_sections(self, data: dict[str, Any]) -> list[CourseSection]:
        """Parse the answer from core_course_get_contents in CourseSection-Dataclasses.

        The Moodle answer is a list of sections, each containing a 'modules'
        array with module details including contents.
        """
        if not isinstance(data, list):
            raise ParseError(f"Course contents ist keine Liste.")

        sections: list[CourseSection] = []
        for raw in data:
            parsed_modules: list[dict[str, Any]] = []
            for mod in raw.get("modules", []):
                modname = mod.get("modname", "")
                # Verfügbarkeit strippen
                availability = _strip_availabilityinfo(mod.get("availabilityinfo"))

                # Modul-Basisinformationen
                module_info: dict[str, Any] = {
                    "id": mod.get("id"),
                    "name": mod.get("name", ""),
                    "modname": modname,
                    "url": mod.get("url"),
                    "visible": mod.get("visible"),
                    "uservisible": mod.get("uservisible", True),
                    "availability": availability,
                }

                # Contents verarbeiten (nur, wenn vorhanden)
                contents = mod.get("contents")
                if contents:
                    module_info["contents"] = contents

                # Additional info for folder modules: extract filepath from contents
                if modname == "folder" and contents:
                    # Extract filepath from the first content item if available
                    for content in contents:
                        if content.get("type") == "file" and content.get("filepath"):
                            module_info["filepath"] = content.get("filepath")
                            break
                    else:
                        module_info["filepath"] = ""

                parsed_modules.append(module_info)

            section = CourseSection(
                id=raw["id"],
                number=raw.get("section", 0),
                name=raw.get("name", ""),
                visible=bool(raw.get("visible", 1)),
                uservisible=raw.get("uservisible", True),
                modules=parsed_modules,
            )
            sections.append(section)
        return sections