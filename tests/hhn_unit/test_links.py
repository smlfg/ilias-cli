"""Unit-Tests für ilias_core.ilias_html.links (Spec §13.5)."""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.links import parse_link


LINK_STYLES = [
    # /go/<typ>/<ref>
    ("https://ilias.example.org/go/crs/900101", "crs", 900101),
    ("https://ilias.example.org/go/fold/900201", "fold", 900201),
    ("https://ilias.example.org/go/grp/900105", "grp", 900105),
    ("https://ilias.example.org/go/exc/900501", "exc", 900501),
    ("https://ilias.example.org/go/tst/900601", "tst", 900601),
    ("https://ilias.example.org/go/cat/900190", "cat", 900190),
    ("https://ilias.example.org/go/root/1", "root", 1),

    # goto.php/<typ>/<ref>
    ("https://ilias.example.org/goto.php/fold/900202", "fold", 900202),
    ("https://ilias.example.org/goto.php/exc/900501", "exc", 900501),

    # goto.php?target=<typ>_<ref>[_download]
    ("https://ilias.example.org/goto.php?target=grp_900105&client_id=testclient", "grp", 900105),
    ("https://ilias.example.org/goto.php?target=file_900301_download", "file", 900301),
    ("https://ilias.example.org/goto.php?target=exc_900501", "exc", 900501),

    # ilias.php?...ref_id=<ref> mit Typtabelle
    ("https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=900301", "file", 900301),
    ("https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmd=sendfile&ref_id=900301", "file", 900301),
    ("https://ilias.example.org/ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=900401&cmd=calldirectlink", "webr", 900401),
    ("https://ilias.example.org/ilias.php?baseClass=ilWikiHandlerGUI&ref_id=900951&cmd=view", "wiki", 900951),
    ("https://ilias.example.org/ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=900501&cmd=showOverview", "exc", 900501),
    ("https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmdClass=ilobjtestgui&ref_id=900601", "tst", 900601),
    # baseClass=ilrepositorygui ohne weiteres Merkmal -> None
    ("https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&ref_id=900211", None, 900211),

    # Relative URLs
    ("/go/crs/900101", "crs", 900101),
    ("goto.php?target=file_900301_download", "file", 900301),

    # Leer / Fragment
    ("#", None, None),
    ("", None, None),
    ("   ", None, None),

    # Case-insensitive
    ("https://ilias.example.org/GO/CRS/900101", "crs", 900101),
    ("https://ilias.example.org/goto.php?TARGET=GRP_900105", "grp", 900105),
]


@pytest.mark.parametrize("href,expected_type,expected_ref", LINK_STYLES)
def test_parse_link(href: str, expected_type: str | None, expected_ref: int | None):
    """§13.5: ref_id/Typ aus allen Link-Formen extrahieren."""
    base = "https://ilias.example.org"
    typ, ref = parse_link(href, base)
    assert typ == expected_type, f"href={href}: expected type {expected_type}, got {typ}"
    assert ref == expected_ref, f"href={href}: expected ref {expected_ref}, got {ref}"


def test_parse_link_unknown_type_table():
    """Unbekannter Typ in Typtabelle -> type=None, aber ref_id vorhanden."""
    href = "https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmdClass=ilUnknownGUI&ref_id=12345"
    typ, ref = parse_link(href, "https://ilias.example.org")
    assert typ is None
    assert ref == 12345


def test_parse_link_no_ref_id():
    """Link ohne ref_id -> (None, None)."""
    href = "https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmd=foo"
    typ, ref = parse_link(href, "https://ilias.example.org")
    assert typ is None
    assert ref is None


def test_parse_link_case_insensitive_query():
    """Query-Werte case-insensitive."""
    href = "https://ilias.example.org/ilias.php?BASECLASS=ILREPOSITORYGUI&CMDCLASS=ILOBJFILEGUI&CMD=SENDFILE&REF_ID=900301"
    typ, ref = parse_link(href, "https://ilias.example.org")
    assert typ == "file"
    assert ref == 900301


def test_parse_link_webr_calldirectlink():
    """Weblink mit calldirectlink -> webr."""
    href = "ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=900401&cmd=calldirectlink"
    typ, ref = parse_link(href, "https://ilias.example.org")
    assert typ == "webr"
    assert ref == 900401