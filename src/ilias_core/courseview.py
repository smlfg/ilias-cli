"""Baum-Ansicht eines Moodle-Kurses (F3): Webseitendaten -> strukturierte Knoten.

Reine Logik in ilias_core: parst die `core_course_get_contents`-Antwort,
baut den Abschnitt/Modul/Knoten-Baum (inkl. verschachtelter Ordner aus
`filepath`) und wendet `--depth` an.
"""

from __future__ import annotations

import html
import re
from typing import Any

from .models import ContentNode, ModuleNode, SectionNode
from .timeutil import epoch_iso

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    """Entfernt HTML-Tags, wandelt Entities um, fasst Whitespace zusammen."""
    if not text:
        return ""
    plain = _TAG_RE.sub("", text)
    plain = html.unescape(plain)
    return _WS_RE.sub(" ", plain).strip()


def label_text(name: str | None) -> str:
    return strip_html(name)[:60]


# -- Ordnerstruktur aus filepath -----------------------------------------
def _folder_path_parts(filepath: str) -> list[str]:
    parts = [p for p in (filepath or "/").split("/") if p]
    return parts


def build_file_tree(contents: list[dict[str, Any]]) -> list[ContentNode]:
    """Moodle-`contents` eines Ordner-Moduls -> geschachtelte Ordner/Dateien.

    `filepath` ("/", "/Blatt 1/", "/Blatt 1/Lösungen/") definiert die
    Ordnerhierarchie; Dateien hängen im letzten Pfadsegment.
    """
    root: list[ContentNode] = []
    folders: dict[str, ContentNode] = {}

    def ensure_folder(path: str) -> ContentNode:
        if path in folders:
            return folders[path]
        parts = _folder_path_parts(path)
        parent_path = "/" + "/".join(parts[:-1]) + "/" if len(parts) > 1 else "/"
        node = ContentNode(type="folder", name=parts[-1] if parts else path, path=path)
        folders[path] = node
        if len(parts) <= 1:
            root.append(node)
        else:
            parent = ensure_folder(parent_path)
            parent.children.append(node)
        return node

    for item in contents:
        if not isinstance(item, dict) or item.get("type") == "url":
            continue
        filepath = item.get("filepath")
        filepath = filepath if isinstance(filepath, str) and filepath else "/"
        if not filepath.endswith("/"):
            filepath += "/"
        parent = root if filepath == "/" else ensure_folder(filepath).children
        parent.append(
            ContentNode(
                type="file",
                name=item.get("filename") or "",
                path=filepath,
                size=item.get("filesize") if isinstance(item.get("filesize"), int) else None,
                mimetype=item.get("mimetype") if isinstance(item.get("mimetype"), str) else None,
                timemodified=epoch_iso(item.get("timemodified")),
                fileurl=item.get("fileurl") if isinstance(item.get("fileurl"), str) else None,
            )
        )
    # Ordnung: Ordner, dann Dateien, jeweils nach Name
    def _sort(nodes: list[ContentNode]) -> list[ContentNode]:
        nodes.sort(key=lambda n: (0 if n.type == "folder" else 1, n.name.lower()))
        for n in nodes:
            _sort(n.children)
        return nodes

    return _sort(root)


# -- Modul-Knoten ----------------------------------------------------------
def _file_node(item: dict[str, Any]) -> ContentNode:
    filepath = item.get("filepath")
    return ContentNode(
        type="file",
        name=item.get("filename") or "",
        path=filepath if isinstance(filepath, str) else None,
        size=item.get("filesize") if isinstance(item.get("filesize"), int) else None,
        mimetype=item.get("mimetype") if isinstance(item.get("mimetype"), str) else None,
        timemodified=epoch_iso(item.get("timemodified")),
        fileurl=item.get("fileurl") if isinstance(item.get("fileurl"), str) else None,
    )


def module_children(mod: dict[str, Any]) -> list[ContentNode]:
    modname = mod.get("modname")
    contents = mod.get("contents")
    if not isinstance(contents, list):
        return []
    if modname == "folder":
        return build_file_tree(contents)
    if modname == "url":
        first = next((c for c in contents if isinstance(c, dict)), None)
        if first is None:
            return []
        return [
            ContentNode(
                type="url",
                name=first.get("filename") or strip_html(mod.get("name")) or "Link",
                url=first.get("fileurl") if isinstance(first.get("fileurl"), str) else None,
            )
        ]
    # resource und alles andere mit Dateien
    files = [c for c in contents if isinstance(c, dict) and c.get("type") in (None, "file")]
    return [_file_node(c) for c in files]


def build_sections(raw_sections: list[dict[str, Any]]) -> list[SectionNode]:
    sections: list[SectionNode] = []
    for raw in raw_sections:
        if not isinstance(raw, dict):
            continue
        modules: list[ModuleNode] = []
        for mod in raw.get("modules") or []:
            if not isinstance(mod, dict):
                continue
            uservisible = mod.get("uservisible", True)
            uservisible = uservisible if isinstance(uservisible, bool) else bool(uservisible)
            availability = None
            if not uservisible:
                info = mod.get("availabilityinfo")
                if isinstance(info, str) and info:
                    availability = strip_html(info)
            raw_name = mod.get("name") if isinstance(mod.get("name"), str) else ""
            name = label_text(raw_name) if mod.get("modname") == "label" else raw_name
            modules.append(
                ModuleNode(
                    id=mod.get("id") if isinstance(mod.get("id"), int) else None,
                    name=name,
                    modname=mod.get("modname") if isinstance(mod.get("modname"), str) else "",
                    url=mod.get("url") if isinstance(mod.get("url"), str) else None,
                    visible=bool(mod.get("visible", 1)),
                    uservisible=uservisible,
                    availability=availability,
                    children=module_children(mod),
                )
            )
        sec_uservisible = raw.get("uservisible", True)
        sec_uservisible = sec_uservisible if isinstance(sec_uservisible, bool) else bool(sec_uservisible)
        sections.append(
            SectionNode(
                id=raw.get("id") if isinstance(raw.get("id"), int) else None,
                number=raw.get("section") if isinstance(raw.get("section"), int) else None,
                name=raw.get("name") if isinstance(raw.get("name"), str) else "",
                visible=bool(raw.get("visible", 1)),
                uservisible=sec_uservisible,
                modules=modules,
            )
        )
    return sections


# -- Depth ------------------------------------------------------------------
def apply_depth(sections: list[SectionNode], depth: int | None) -> list[SectionNode]:
    """Kürzt den Baum: 1=Abschnitte, 2=+Module, 3=+Dateien/erste Ordner­ebene,
    jede weitere Ebene = eine Ordner­ebene mehr. None = alles."""
    for section in sections:
        if depth is not None and depth < 2:
            section.modules = []
            continue
        for module in section.modules:
            if depth is not None and depth < 3:
                module.children = []
            else:
                module.children = _prune_nodes(module.children, level=3, depth=depth)
    return sections


def _prune_nodes(nodes: list[ContentNode], *, level: int, depth: int | None) -> list[ContentNode]:
    if depth is not None and level > depth:
        return []
    for node in nodes:
        if node.type == "folder":
            node.children = _prune_nodes(node.children, level=level + 1, depth=depth)
    return nodes
