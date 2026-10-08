"""Kleine, implementierungsneutrale Helfer zum Durchsuchen der JSON-Ausgaben von ls/courses."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

# Erlaubte Typ-Bezeichner pro Objektart (ILIAS-Kürzel oder sprechender Name), Spec §6.2
KINDS = {
    "folder": {"folder", "fold"},
    "file": {"file"},
    "url": {"url", "webr", "link"},
    "exercise": {"exc", "exercise"},
    "test": {"tst", "test"},
    "forum": {"frm", "forum"},
}


def kind(node: dict[str, Any]) -> str:
    """Typ eines Knotens: `type` (verschachtelte Knoten) oder `modname` (oberste Ebene)."""
    t = node.get("type")
    if t in (None, "item", "module", "object"):
        t = node.get("modname") or t
    return str(t)


def children(node: dict[str, Any]) -> list[dict[str, Any]]:
    return list(node.get("children") or []) + list(node.get("modules") or [])


def walk(nodes: list[dict[str, Any]]) -> Iterator[tuple[int, dict[str, Any]]]:
    """(Ebene, Knoten) für alle Knoten; Ebene 1 = Abschnitt, 2 = Objekt im Kurs, 3+ = in Ordnern."""
    stack = [(1, n) for n in reversed(nodes)]
    while stack:
        level, node = stack.pop()
        yield level, node
        for child in reversed(children(node)):
            stack.append((level + 1, child))


def find(data: dict[str, Any], name: str) -> dict[str, Any]:
    hits = [n for _, n in walk(data.get("sections", [])) if n.get("name") == name]
    assert hits, f"Knoten {name!r} nicht gefunden in {[n.get('name') for _, n in walk(data.get('sections', []))]}"
    assert len(hits) == 1, f"Knoten {name!r} {len(hits)}x gefunden (doppelte Einträge?)"
    return hits[0]


def names(data: dict[str, Any]) -> list[str]:
    return [n.get("name") for _, n in walk(data.get("sections", []))]


def max_level(data: dict[str, Any]) -> int:
    return max((lvl for lvl, _ in walk(data.get("sections", []))), default=0)
