"""Parser für Container-Seiten (Kurs, Ordner, Gruppe) (Spec §6, §13.3).

Pure Funktionen, kein I/O. Legacy-Liste: .ilContainerBlock -> Abschnitte,
.ilContainerListItemOuter -> Module.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from .links import parse_link, parse_link_from_item
from .props import extract_file_props, extract_suffix

if TYPE_CHECKING:
    from typing import List, Optional


@dataclass(frozen=True)
class ContainerItem:
    """Ein Eintrag in der Container-Liste (Modul, Datei, Ordner, Link, etc.)."""
    ref_id: int
    type: str  # fold, file, webr, exc, tst, frm, sess, itgr, lm, htlm, copa, mcst, wiki, blog, grp, crsr, cat, other, ...
    title: str
    url: str
    visible: bool
    props: list[str]  # Roh-Eigenschaften für Dateien
    inline: bool  # Datei mit eigenem Icon (deliver.php)
    target_ref_id: int | None  # für crsr: Ziel-Kurs ref_id
    icon_alt: str | None  # Fallback für Typ-Bestimmung


@dataclass(frozen=True)
class ContainerBlock:
    """Ein Block (Abschnitt) auf der Container-Seite."""
    title: str
    itgr_ref_id: int | None  # Objektblock-ID falls itgr
    items: List[ContainerItem]


# Selektoren (mit Fallbacks)
CONTAINER_BLOCK_SELECTOR = ".ilContainerBlock.form-inline"
BLOCK_HEADER_SELECTOR = ".ilContainerBlockHeader h2.ilContainerBlockHeader"
ITEMS_CONTAINER_SELECTOR = ".ilContainerItemsContainer"
LIST_ITEM_OUTER_SELECTOR = ".ilContainerListItemOuter"
LIST_ITEM_ICON_SELECTOR = ".ilContainerListItemIcon img.ilListItemIcon"
LIST_ITEM_CONTENT_SELECTOR = ".ilContainerListItemContent"
TITLE_LINK_SELECTOR = "h3.il_ContainerItemTitle a.il_ContainerItemTitle"
ACTIONS_SELECTOR = ".ilFloatRight"
DESCRIPTION_SELECTOR = ".il_Description"
PROPERTIES_SELECTOR = ".il_ItemProperties .il_ItemProperty"
ALERT_PROPERTIES_SELECTOR = ".il_ItemAlertProperties .il_ItemAlertProperty"
EXPAND_SELECTOR = ".ilListItemSection a[href*='expand=']"


# Typ-Mapping von Icon-Alt-Text zu Typ-Kürzel
ICON_TYPE_MAP = {
    "ordner": "fold",
    "datei": "file",
    "inline datei": "file",
    "weblink": "webr",
    "übung": "exc",
    "test": "tst",
    "forum": "frm",
    "sitzung": "sess",
    "objektblock": "itgr",
    "lernszenario": "lm",
    "html-seite": "htlm",
    "copa": "copa",
    "multiple-choice": "mcst",
    "wiki": "wiki",
    "blog": "blog",
    "gruppe": "grp",
    "kurslink": "crsr",
    "kategorie": "cat",
}


def normalize_text(text: str) -> str:
    """HTML-Entities dekodieren, NFC normalisieren, Whitespace normalisieren, nie kürzen."""
    if not text:
        return ""
    text = text.replace("&nbsp;", " ")
    text = unicodedata.normalize("NFC", text)
    text = " ".join(text.split())
    return text


def parse_container(html: str, base_url: str, parent_ref_id: int) -> list[ContainerBlock]:
    """Container-Seite parsen (Kurs, Ordner, Gruppe) (Spec §13.3).

    Args:
        html: Vollständiges HTML der Seite
        base_url: Basis-URL der ILIAS-Instanz
        parent_ref_id: ref_id des Containers (für data-list-item-id)

    Returns:
        Liste von ContainerBlock (Abschnitte in Seitenreihenfolge)
    """
    soup = BeautifulSoup(html, "html.parser")

    # Hauptinhalt: #ilContentContainer #il_center_col
    center_col = soup.select_one("#ilContentContainer #il_center_col")
    if not center_col:
        return []

    blocks = []

    for block_el in center_col.select(CONTAINER_BLOCK_SELECTOR):
        # Block-Titel
        header = block_el.select_one(BLOCK_HEADER_SELECTOR)
        block_title = normalize_text(header.get_text()) if header else "Inhalt"

        # itgr_ref_id aus data-store-url
        itgr_ref_id = None
        store_url = block_el.get("data-store-url", "")
        if "cont_block_id=itgr_" in store_url:
            try:
                itgr_ref_id = int(store_url.split("cont_block_id=itgr_")[1].split("&")[0].split('"')[0])
            except (ValueError, IndexError):
                pass

        # Items im Block
        items_container = block_el.select_one(ITEMS_CONTAINER_SELECTOR)
        if not items_container:
            blocks.append(ContainerBlock(title=block_title, itgr_ref_id=itgr_ref_id, items=[]))
            continue

        items = []
        seen_ref_ids = set()

        for item_outer in items_container.select(LIST_ITEM_OUTER_SELECTOR):
            # Ref_id primär aus data-list-item-id
            item = parse_container_item(item_outer, base_url, parent_ref_id)
            if item and item.ref_id not in seen_ref_ids:
                seen_ref_ids.add(item.ref_id)
                items.append(item)

        blocks.append(ContainerBlock(title=block_title, itgr_ref_id=itgr_ref_id, items=items))

    return blocks


def parse_container_item(item_outer, base_url: str, parent_ref_id: int) -> ContainerItem | None:
    """Einzelnes .ilContainerListItemOuter parsen."""
    # Icon
    icon_el = item_outer.select_one(LIST_ITEM_ICON_SELECTOR)
    icon_alt = icon_el.get("alt") if icon_el else None
    icon_title = icon_el.get("title") if icon_el else None

    # Titel-Link (nur a.il_ContainerItemTitle, nicht h3, nicht .glyph, nicht href="#")
    title_link = item_outer.select_one(TITLE_LINK_SELECTOR)
    if not title_link or not title_link.get("href"):
        return None

    href = title_link["href"]
    if href.strip() == "#":
        return None

    title = normalize_text(title_link.get_text())

    # Typ und ref_id aus Link + data-list-item-id
    typ, ref_id = parse_link_from_item(item_outer, base_url)

    # Fallback: Icon für Typ
    if typ is None:
        typ = guess_type_from_icon(icon_alt, icon_title)

    # Unbekannte Typen -> "other" (nicht "unknown", damit JSON stabil)
    if typ is None:
        typ = "other"

    # ref_id muss vorhanden sein
    if ref_id is None:
        return None

    # Eigenschaften
    props = []
    props_el = item_outer.select(PROPERTIES_SELECTOR)
    for p in props_el:
        prop_text = normalize_text(p.get_text())
        if prop_text:
            props.append(prop_text)

    # Offline
    offline = False
    alert_el = item_outer.select_one(ALERT_PROPERTIES_SELECTOR)
    if alert_el and "offline" in alert_el.get_text().lower():
        offline = True

    # Inline-Datei (eigenes Symbol, a.glyph mit href="#")
    inline = False
    glyph = item_outer.select_one("a.glyph[href='#']")
    if glyph:
        inline = True

    # Expand-Link für Sitzungen (nicht folgen, nur erkennen)
    expand_link = item_outer.select_one(EXPAND_SELECTOR)
    is_session = expand_link is not None

    # Für crsr: target_ref_id aus Link
    target_ref_id = None
    if typ == "crsr":
        _, target_ref_id = parse_link(href, base_url)

    # URL absolut machen
    url = href
    if not url.startswith(("http://", "https://")):
        from urllib.parse import urljoin
        url = urljoin(base_url, url)

    return ContainerItem(
        ref_id=ref_id,
        type=typ,
        title=title,
        url=url,
        visible=not offline,
        props=props,
        inline=inline,
        target_ref_id=target_ref_id,
        icon_alt=icon_alt,
    )


def guess_type_from_icon(alt: str | None, title: str | None) -> str | None:
    """Typ aus Icon-Alt/Title raten (Fallback, Spec §13.3)."""
    for text in (alt, title):
        if not text:
            continue
        text_lower = text.lower()
        for keyword, typ in ICON_TYPE_MAP.items():
            if keyword in text_lower:
                return typ
    return None


def item_to_module(item: ContainerItem, base_url: str, path: str = "/") -> dict:
    """ContainerItem in Modul-Dict für JSON-Ausgabe umwandeln."""
    from urllib.parse import urljoin

    # Pfad für Kinder
    child_path = f"{path}{item.title}/" if item.type in ("fold", "grp") else path

    # Basis-Modul
    module = {
        "id": item.ref_id,
        "ref_id": item.ref_id,
        "name": item.title,
        "modname": item.type,
        "url": item.url,
        "visible": item.visible,
        "uservisible": item.visible,
        "availability": None,
        "children": [],
    }

    # Typ-spezifische Felder
    if item.type in ("fold", "grp"):
        module["type"] = "folder"
        module["path"] = child_path
    elif item.type == "file":
        file_props = extract_file_props(item.props)
        module["type"] = "file"
        module["path"] = path
        module["size"] = file_props["size"]
        module["size_text"] = file_props["size_text"]
        module["suffix"] = file_props["suffix"]
        module["mimetype"] = None
        module["timemodified"] = file_props["timemodified"]
        # fileurl: Download-Link der Datei (Titel-Link ist oft schon der Download-Link)
        fileurl = item.url
        if "cmd=sendfile" not in fileurl and "file_" not in fileurl:
            # Falls nicht, Download-Link konstruieren
            fileurl = urljoin(base_url, f"ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjFileGUI&cmd=sendfile&ref_id={item.ref_id}")
        module["fileurl"] = fileurl
    elif item.type == "webr":
        module["type"] = "url"
        module["target_url"] = None  # wird nicht aufgelöst (Spec §6.2)
    elif item.type == "exc":
        module["type"] = "item"
    elif item.type == "tst":
        module["type"] = "item"
    elif item.type == "frm":
        module["type"] = "item"
    elif item.type == "wiki":
        module["type"] = "item"
    elif item.type == "crsr":
        module["type"] = "course_link"
        module["target_ref_id"] = item.target_ref_id
    elif item.type == "sess":
        module["type"] = "session"
        module["children"] = None  # nicht expandieren (Spec §13.6)
    elif item.type == "grp":
        module["type"] = "folder"
        module["path"] = child_path
    else:
        module["type"] = "item"

    return module