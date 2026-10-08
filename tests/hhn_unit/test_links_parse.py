"""Unit-Tests des zentralen Link-Parsers (Spec §13.5, S6-Grundlage für S7)."""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.links import parse_link

BASE = "https://ilias.example.org"


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        # 1. /go/<typ>/<ref>
        ("/go/crs/900101", ("crs", 900101)),
        ("https://ilias.example.org/go/grp/900105", ("grp", 900105)),
        # 2. goto.php/<typ>/<ref>
        ("/goto.php/crs/900101", ("crs", 900101)),
        # 3. goto.php?target=<typ>_<ref>[_download]
        ("/goto.php?target=crs_900101", ("crs", 900101)),
        ("/goto.php?target=file_900301_download", ("file", 900301)),
        # 4. ilias.php mit Typtabelle
        ("ilias.php?baseClass=ilObjFileGUI&cmd=sendfile&ref_id=900301", ("file", 900301)),
        (
            "ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=900401&cmd=calldirectlink",
            ("webr", 900401),
        ),
        ("ilias.php?baseClass=ilWikiHandlerGUI&ref_id=900951&cmd=view", ("wiki", 900951)),
        ("ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=900501", ("exc", 900501)),
        (
            "ilias.php?baseClass=ilrepositorygui&cmdClass=ilobjtestgui&ref_id=900601",
            ("tst", 900601),
        ),
        # baseClass=ilrepositorygui ohne weiteres Merkmal -> Typ None (Symbol entscheidet)
        ("ilias.php?baseClass=ilrepositorygui&ref_id=900101", (None, 900101)),
        # Sonderfälle
        ("ilias.php?CMD=sendfile&REF_ID=900302", ("file", 900302)),
        ("#", (None, None)),
        ("", (None, None)),
    ],
)
def test_parse_link(href, expected):
    assert parse_link(href, BASE) == expected
