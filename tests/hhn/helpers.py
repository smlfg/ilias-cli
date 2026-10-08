"""Kleine, implementierungsneutrale Helfer zum Durchsuchen der JSON-Ausgaben von ls/courses."""

from __future__ import annotations

import json
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
    "wiki": {"wiki"},
    "course_link": {"crsr"},
    "session": {"sess", "session"},
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


def ref_ids(data: dict[str, Any]) -> list[int]:
    """ref_id aller Objekt-Knoten (Abschnitte ausgenommen), in Ausgabe-Reihenfolge."""
    return [n.get("ref_id") or n.get("id") for lvl, n in walk(data.get("sections", [])) if lvl >= 2]


def max_level(data: dict[str, Any]) -> int:
    return max((lvl for lvl, _ in walk(data.get("sections", []))), default=0)


# --------------------------------------------------------------------------- CLI-Ergebnisse
NOT_A_COMMAND = ("No such command", "Usage:")  # typer-Fehler zählen nicht als korrektes Verhalten


def ok_json(r) -> dict:
    assert r.exit_code == 0, str(r)
    return json.loads(r.stdout)


def err_json(r, code: int, error_code: str | None = None) -> dict:
    assert r.exit_code == code, str(r)
    assert not any(s in r.stderr for s in NOT_A_COMMAND), f"Befehl fehlt/Usage-Fehler statt Fachfehler:\n{r}"
    data = json.loads(r.stdout)
    assert data.get("ok") is False, data
    if error_code:
        assert data["error"]["code"] == error_code, data
    return data


def ilias_gets(h) -> list:
    return [r for r in h.world.requests_to("ilias") if r.method == "GET"]
