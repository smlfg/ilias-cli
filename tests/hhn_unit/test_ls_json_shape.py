"""JSON-Form von `ls` für ILIAS (Spec §6.2): children null bleibt null, ref_id neben id, target_url bei Weblinks."""

from __future__ import annotations

from ilias_core.models import ItemNode, Module, Section
from ilias_core.service import trim_sections


def _section() -> Section:
    return Section(
        id=1,
        number=0,
        name="Inhalt",
        modules=[
            Module(id=900301, ref_id=900301, name="Sitzung 1", modname="sess", children=None),
            Module(id=900302, ref_id=900302, name="Kurslink", modname="crsr", children=None),
            Module(id=900303, ref_id=900303, name="Ordner", modname="fold", children=[]),
            Module(id=900304, ref_id=900304, name="Weblink", modname="webr", url="https://ilias.example.org/x"),
        ],
    )


def test_trim_depth2_keeps_children_null_for_sessions_and_course_links():
    for depth in (2, 3, None):
        modules = trim_sections([_section()], depth)[0].modules
        assert modules[0].to_json_dict()["children"] is None
        assert modules[1].to_json_dict()["children"] is None
        assert modules[2].to_json_dict()["children"] == []


def test_module_ref_id_next_to_id_and_weblink_target_url_null():
    data = [m.to_json_dict() for m in _section().modules]
    assert all(d["ref_id"] == d["id"] for d in data)
    assert list(data[0])[:2] == ["id", "ref_id"]
    assert data[3]["target_url"] is None
    assert "target_url" not in data[2]


def test_moodle_module_has_no_ilias_only_keys():
    data = Module(id=7, name="Link", modname="url", url="https://example.org").to_json_dict()
    assert "ref_id" not in data and "target_url" not in data


def test_item_node_weblink_target_url_null():
    node = ItemNode(name="Weblink", modname="webr", ref_id=900305, url="https://ilias.example.org/y")
    assert node.to_json_dict()["target_url"] is None
    assert "target_url" not in ItemNode(name="Übung", modname="exc", ref_id=900306).to_json_dict()
