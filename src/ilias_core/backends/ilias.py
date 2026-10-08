"""ILIAS-Backend: Adapter über :class:`ilias_core.client.IliasClient`.

Login (OIDC/Keycloak + TOTP für HHN, SAML/Shibboleth für Uni Mannheim), Verifikation
gegen das Dashboard, Session-Cookies im Keyring bzw. in einer 0600-Datei.
Kurse (F2) und Kursinhalt (F3) per HTML-Scraping.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..client import IliasClient
from ..errors import CrawlLimitError, IliasError, NotSupportedError, ParserError
from ..ilias_html import fetch_page
from ..ilias_html.container import ContainerBlock, ContainerItem, parse_container
from ..ilias_html.membership import Membership, parse_memberships
from ..models import (
    Course,
    Credentials,
    FolderNode,
    FileNode,
    ItemNode,
    LoginResult,
    LogoutResult,
    Module,
    Section,
    SessionNode,
    SessionStatus,
    UrlNode,
    CourseLinkNode,
)
from .base import Backend

if TYPE_CHECKING:
    from ..models import ContentNode


class IliasBackend(Backend):
    name = "ilias"
    supports_login = True
    supports_courses = True

    def __init__(self, instance, *, client: IliasClient | None = None) -> None:
        super().__init__(instance)
        self.client = client or IliasClient(instance)

    @property
    def uses_totp(self) -> bool:
        return self.client.uses_totp

    def login(
        self, credentials: Credentials, otp_callback: Callable[[], str] | None = None
    ) -> LoginResult:
        return self.client.login(credentials.username, credentials.password.reveal(), otp_callback)

    def login_with_browser(self) -> LoginResult:
        return self.client.login_with_browser()

    def status(self) -> SessionStatus:
        return self.client.status()

    def logout(self) -> LogoutResult:
        removed = self.client.logout()
        return LogoutResult(instance=self.instance.key, lms=self.instance.lms, token_removed=removed)

    def courses(self) -> list[Course]:
        """Kurse aus 'Meine Kurse und Gruppen' laden (ilmembershipoverviewgui)."""
        url = f"{self.instance.base_url.rstrip('/')}/ilias.php?baseClass=ilmembershipoverviewgui"
        html = fetch_page(self.instance, url, page_type="membership")
        memberships = parse_memberships(html, self.instance.base_url)

        courses = []
        for m in memberships:
            courses.append(Course(
                id=m.ref_id,
                fullname=m.title,
                shortname="",
                category=None,
                semester=m.semester,
                visible=m.visible,
                startdate=None,
                enddate=None,
                url=m.url,
                description=m.description,
            ))
        return courses

    def course_contents(self, course_id: int) -> list[Section]:
        """Kursinhalt laden und rekursiv Ordner/Gruppen auflösen (Spec §6, §13.8).

        Gibt den vollständigen Baum zurück (ohne Depth-Begrenzung).
        Depth-Trimming passiert in Service.ls() via trim_sections().
        Crawl-Schutz: visited-Set über ref_id, harte Request-Obergrenze.
        """
        max_requests = int(os.environ.get("ILIAS_CLI_MAX_REQUESTS", "300"))
        visited: set[int] = set()
        request_count = 0

        def load_container(ref_id: int, parent_path: str = "/") -> list[ContainerBlock]:
            nonlocal request_count
            if request_count >= max_requests:
                raise CrawlLimitError(
                    f"Request-Limit ({max_requests}) erreicht. Crawl abgebrochen.",
                    hint="`ilias ls` mit geringerem --depth oder größerer ILIAS_CLI_MAX_REQUESTS wiederholen.",
                )
            if ref_id in visited:
                return []
            visited.add(ref_id)

            url = f"{self.instance.base_url.rstrip('/')}/ilias.php?baseClass=ilrepositorygui&ref_id={ref_id}"
            request_count += 1
            html = fetch_page(self.instance, url, page_type="container", requested_ref_id=ref_id)
            return parse_container(html, self.instance.base_url, ref_id)

        def item_to_content_node(item: ContainerItem, base_path: str) -> "ContentNode":
            """ContainerItem in ContentNode (FolderNode, FileNode, etc.) umwandeln."""
            child_path = f"{base_path}{item.title}/" if item.type in ("fold", "grp") else base_path

            if item.type in ("fold", "grp"):
                # Ordner: Kinder werden später rekursiv hinzugefügt
                return FolderNode(
                    name=item.title,
                    path=child_path,
                    ref_id=item.ref_id,
                    url=item.url,
                    visible=item.visible,
                    children=[],
                )
            elif item.type == "file":
                from ..ilias_html.props import extract_file_props
                file_props = extract_file_props(item.props)
                return FileNode(
                    name=item.title,
                    path=base_path,
                    ref_id=item.ref_id,
                    fileurl=item.url,
                    size=file_props["size"],
                    size_text=file_props["size_text"],
                    suffix=file_props["suffix"],
                    mimetype=None,
                    timemodified=file_props["timemodified"],
                    visible=item.visible,
                )
            elif item.type == "webr":
                return UrlNode(
                    name=item.title,
                    url=item.url,
                    ref_id=item.ref_id,
                    visible=item.visible,
                    target_url=None,
                )
            elif item.type in ("exc", "tst", "frm", "wiki", "lm", "htlm", "copa", "mcst", "blog"):
                return ItemNode(
                    name=item.title,
                    modname=item.type,
                    ref_id=item.ref_id,
                    url=item.url,
                    visible=item.visible,
                )
            elif item.type == "crsr":
                return CourseLinkNode(
                    name=item.title,
                    ref_id=item.ref_id,
                    url=item.url,
                    target_ref_id=item.target_ref_id or 0,
                    visible=item.visible,
                )
            elif item.type == "sess":
                return SessionNode(
                    name=item.title,
                    ref_id=item.ref_id,
                    url=item.url,
                    visible=item.visible,
                )
            else:
                # Unbekannte Typen als generisches Item
                return ItemNode(
                    name=item.title,
                    modname=item.type,
                    ref_id=item.ref_id,
                    url=item.url,
                    visible=item.visible,
                )

        def build_module_children(item: ContainerItem, base_path: str) -> list["ContentNode"]:
            """Kinder für einen Ordner/Gruppe rekursiv laden."""
            if item.type not in ("fold", "grp"):
                return []

            child_path = f"{base_path}{item.title}/"
            child_blocks = load_container(item.ref_id, child_path)
            children = []
            for block in child_blocks:
                for child_item in block.items:
                    child_node = item_to_content_node(child_item, child_path)
                    # Rekursion für Unterordner
                    if child_item.type in ("fold", "grp"):
                        if isinstance(child_node, FolderNode):
                            grand_children = build_module_children(child_item, child_path)
                            child_node = FolderNode(
                                name=child_node.name,
                                path=child_node.path,
                                ref_id=child_node.ref_id,
                                url=child_node.url,
                                visible=child_node.visible,
                                children=grand_children,
                            )
                    children.append(child_node)
            return children

        def build_modules(blocks: list[ContainerBlock], base_path: str) -> list[Module]:
            """Module aus Blöcken bauen."""
            modules = []
            for block in blocks:
                for item in block.items:
                    # Kinder für Ordner/Gruppen
                    if item.type in ("fold", "grp"):
                        children = build_module_children(item, base_path)
                    elif item.type == "sess":
                        children = None  # Spec §13.6
                    else:
                        children = []

                    module = Module(
                        id=item.ref_id,
                        name=item.title,
                        modname=item.type,
                        url=item.url,
                        visible=item.visible,
                        uservisible=item.visible,
                        availability=None,
                        children=children,
                    )
                    modules.append(module)
            return modules

        # Haupteinstieg: Kurs-Container laden
        blocks = load_container(course_id)

        # In Sections umwandeln
        sections = []
        for block_idx, block in enumerate(blocks):
            modules = build_modules([block], "/")
            sections.append(Section(
                id=block.itgr_ref_id or (course_id * 1000 + block_idx + 1),
                number=block_idx,
                name=block.title,
                visible=True,
                uservisible=True,
                modules=modules,
            ))
        return sections