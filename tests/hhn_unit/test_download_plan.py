"""Reine Funktionen von F5 (`ilias_core.download`, Content-Disposition), ohne Netz."""

from __future__ import annotations

import unicodedata

from ilias_core import download as dl
from ilias_core.ilias_html.fetch import _disposition_filename
from ilias_core.models import FileNode, FolderNode, ItemNode, Module, Section


def _sections():
    sub = FolderNode(name="Lösungen", path="/Blätter/Lösungen/", ref_id=12, children=[
        FileNode(name="Lösung 1", path="/Blätter/Lösungen/", fileurl="u3", suffix="pdf", ref_id=31, timemodified="t3"),
    ])
    fold = Module(id=10, ref_id=10, name="Blätter", modname="fold", children=[
        FileNode(name="Blatt 1", path="/Blätter/", fileurl="u1", suffix="pdf", ref_id=21),
        FileNode(name="Blatt 1", path="/Blätter/", fileurl="u2", suffix="pdf", ref_id=22),
        sub,
        ItemNode(name="Abgabe", modname="exc", ref_id=40),
    ])
    top = Module(id=50, ref_id=50, name="Skript: Teil 1/2", modname="file", fileurl="u5", suffix="pdf")
    link = Module(id=60, ref_id=60, name="Link", modname="webr", url="x")
    return [Section(id=1, number=0, name="Inhalt", modules=[fold, top, link])]


def test_plan_structure_and_dedupe():
    files = dl.plan_files(_sections())
    assert [f.relpath for f in files] == [
        "Blätter/Blatt 1.pdf",
        "Blätter/Blatt 1 (22).pdf",
        "Blätter/Lösungen/Lösung 1.pdf",
        "Skript_ Teil 1-2.pdf",
    ]
    assert [f.ref_id for f in files] == [21, 22, 31, 50]


def test_select_by_path_ref_and_prefix():
    files = dl.plan_files(_sections())
    assert [f.ref_id for f in dl.select(files, "blätter")] == [21, 22, 31]
    assert [f.ref_id for f in dl.select(files, "Blätter/Lösungen")] == [31]
    assert [f.ref_id for f in dl.select(files, "/Blätter/Lösungen/Lösung 1/")] == [31]
    assert [f.ref_id for f in dl.select(files, "31")] == [31]
    assert dl.select(files, "Blät") == []  # nur ganze Pfadteile, kein Teilstring
    assert dl.select(files, None) == files


def test_safe_name():
    assert dl.safe_name("WiSe 2026/27") == "WiSe 2026-27"
    assert dl.safe_name('a:b*c?"d<e>|f') == "a_b_c__d_e__f"
    assert dl.safe_name("  ..  ") == "_"
    assert dl.safe_name(unicodedata.normalize("NFD", "Übung")) == "Übung"
    assert dl.file_name("Blatt.PDF", "pdf") == "Blatt.PDF"
    assert dl.file_name("Blatt", None) == "Blatt"


def test_is_current_and_manifest(tmp_path):
    planned = dl.plan_files(_sections())[0]
    assert not dl.is_current(planned, tmp_path, {})
    (tmp_path / "Blätter").mkdir()
    (tmp_path / planned.relpath).write_bytes(b"x")
    assert dl.is_current(planned, tmp_path, {})  # von Hand abgelegt: nicht überschreiben
    manifest = {"21": {"relpath": planned.relpath, "timemodified": "alt"}}
    assert not dl.is_current(planned, tmp_path, manifest)  # in ILIAS geändert
    dl.save_manifest(tmp_path, {"21": {"relpath": planned.relpath, "timemodified": None}})
    assert dl.is_current(planned, tmp_path, dl.load_manifest(tmp_path))
    (tmp_path / dl.MANIFEST_NAME).write_text("{kaputt")
    assert dl.load_manifest(tmp_path) == {}


def test_disposition_filename():
    assert _disposition_filename("attachment; filename*=UTF-8''L%C3%B6sung%201.pdf") == "Lösung 1.pdf"
    assert _disposition_filename('inline; filename="a b.pdf"') == "a b.pdf"
    assert _disposition_filename(None) is None
