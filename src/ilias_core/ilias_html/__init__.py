"""ILIAS HTML Parser Package.

Pure Parser-Funktionen für verschiedene ILIAS-Seitentypen.
Kein I/O, nur HTML-String + base_url -> Dataclasses/Dicts.
"""

from .container import ContainerBlock, ContainerItem, parse_container, item_to_module
from .fetch import fetch_page
from .links import parse_link, parse_link_from_item
from .membership import Membership, parse_memberships
from .props import extract_file_props, extract_suffix, parse_date, parse_size

__all__ = [
    "ContainerBlock",
    "ContainerItem",
    "parse_container",
    "item_to_module",
    "fetch_page",
    "parse_link",
    "parse_link_from_item",
    "Membership",
    "parse_memberships",
    "extract_file_props",
    "extract_suffix",
    "parse_date",
    "parse_size",
]