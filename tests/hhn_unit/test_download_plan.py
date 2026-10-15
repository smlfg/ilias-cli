"""Reine Funktionen von F5 (`ilias_core.download`, Content-Disposition), ohne Netz."""

from __future__ import annotations

import unicodedata

import pytest

from ilias_core import download as dl
from ilias_core.errors import UnsafePathError
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


# ---------------------------------------------------------------- SEC-16: Namen und Zielpfade
@pytest.mark.parametrize(
    "raw",
    ["CON", "con", "Prn.txt", "AUX.tar.gz", "nul", "COM1", "com9.pdf", "LPT1", "lpt5.doc", "CON .txt"],
)
def test_safe_name_windows_reserved(raw):
    got = dl.safe_name(raw)
    assert got.startswith("_"), got
    assert got.split(".", 1)[0].strip().upper() not in dl._WINDOWS_RESERVED


@pytest.mark.parametrize("raw", ["CONSOLE", "Auxiliar.pdf", "COM10", "LPT0", "NULL", "Contoso"])
def test_safe_name_not_reserved_unchanged(raw):
    assert dl.safe_name(raw) == raw


@pytest.mark.parametrize("raw", ["", ".", "..", "...", " . . ", "\x00", None])
def test_safe_name_empty_or_dots(raw):
    assert dl.safe_name(raw) == "_" or dl.safe_name(raw).strip("_") == ""
    assert dl.safe_name(raw) not in ("", ".", "..")


def test_safe_name_truncation_does_not_end_in_dot():
    got = dl.safe_name("a" * 179 + ". rest")
    assert len(got) <= 180 and not got.endswith((".", " "))


def test_folder_named_dotdot_stays_inside():
    fold = Module(id=2, ref_id=2, name="..", modname="fold", children=[
        FileNode(name="x", path="/../", fileurl="/f", suffix="pdf", ref_id=3),
    ])
    sections = [Section(id=1, number=0, name="Inhalt", modules=[fold])]
    planned = dl.plan_files(sections)
    assert [p.relpath for p in planned] == ["_/x.pdf"]


def test_confined_path_ok(tmp_path):
    course = tmp_path / "Kurs"
    assert dl.confined_path(course, "a/b.pdf", root=tmp_path) == course / "a" / "b.pdf"


@pytest.mark.parametrize("rel", ["../evil.pdf", "a/../../evil.pdf", "/etc/passwd", "", "./x", "a//b"])
def test_confined_path_rejects_traversal(tmp_path, rel):
    with pytest.raises(UnsafePathError) as excinfo:
        dl.confined_path(tmp_path / "Kurs", rel, root=tmp_path)
    assert excinfo.value.exit_code == 1 and excinfo.value.code == "unsafe_path"


def test_confined_path_rejects_resolved_escape(tmp_path):
    """Ein Symlink im Pfad, der nach außen zeigt, fällt spätestens bei resolve() auf."""
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "out"
    (root / "Kurs").mkdir(parents=True)
    (root / "Kurs" / "sub").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        dl.confined_path(root / "Kurs", "sub/x.pdf", root=root)
