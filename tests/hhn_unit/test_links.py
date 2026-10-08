"""Unit-Tests für ``ilias_core.ilias_html.links.parse_link`` (Spec §13.5)."""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.links import parse_link

BASE = "https://ilias.example.org"


@pytest.mark.parametrize(
    "href,expected",
    [
        (f"{BASE}/go/crs/900101", ("crs", 900101)),
        (f"{BASE}/go/fold/900201", ("fold", 900201)),
        ("goto.php/fold/900202", ("fold", 900202)),
        ("goto.php?target=grp_900105&client_id=x", ("grp", 900105)),
        ("goto.php?target=file_900301_download", ("file", 900301)),
        (
            "ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=900301",
            ("file", 900301),
        ),
        (
            "ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=900401&cmd=calldirectlink",
            ("webr", 900401),
        ),
        ("ilias.php?baseClass=ilWikiHandlerGUI&ref_id=900951&cmd=view", ("wiki", 900951)),
        ("ilias.php?baseClass=ilExerciseHandlerGUI&ref_id=900501&cmd=showOverview", ("exc", 900501)),
        ("ilias.php?baseClass=ilrepositorygui&cmdClass=ilobjtestgui&ref_id=900601", ("tst", 900601)),
        ("ilias.php?baseClass=ilrepositorygui&ref_id=900211", (None, 900211)),
        ("#", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
        (f"{BASE}/go/xvid/900801", ("xvid", 900801)),
    ],
)
def test_parse_link(href, expected):
    assert parse_link(href, BASE) == expected


def test_parse_link_case_insensitive_query_values():
    assert parse_link("ilias.php?baseClass=ILREPOSITORYGUI&ref_id=42", BASE) == (None, 42)
    assert parse_link("ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjTestGUI&ref_id=42", BASE) == ("tst", 42)
