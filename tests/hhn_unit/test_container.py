"""Unit-Tests für den Container-Parser (``ilias_core.ilias_html.container``).

Nur synthetisches HTML, das die Live-Struktur aus Spec §13.3 nachbildet
(Objektblock ``itgr``, Legacy-Liste, Doppel-Falle ``il_ContainerItemTitle``).
"""

from __future__ import annotations

from ilias_core.ilias_html.container import (
    flatten_items,
    has_container_structure,
    is_empty_container,
    parse_container,
)

HTML = """
<div id="ilContentContainer"><div id="il_center_col">
 <div class="ilContainerBlock form-inline" data-behaviour="0"
      data-store-url="./ilias.php?baseClass=ilcontainerblockpropertiesstoragegui&amp;cmd=store&amp;cont_block_id=itgr_900181" id="bl_cntr_1">
  <div class="ilContainerBlockHeader"><h2 class="ilHeader ilContainerBlockHeader">Objektblock</h2></div>
  <div class="ilContainerItemsContainer">
   <div class="ilCLI ilObjListRow" id="item_row_900181-900203">
    <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900203_pref_900101">
     <div class="ilContainerListItemIcon"><img alt="Ordner" class="ilListItemIcon" src="./templates/default/images/standard/icon_fold.svg"/></div>
     <div class="ilContainerListItemContent"><div class="il_ContainerListItem">
      <div class="il_ContainerItemTitle form-inline"><h3 class="il_ContainerItemTitle">
       <a class="il_ContainerItemTitle" href="/go/fold/900203">Klausurordner</a>
      </h3></div>
      <div class="ilFloatRight"><ul class="dropdown-menu">
       <li><a href="#" role="menuitem"><span>Notizen</span></a></li></ul></div>
      <div class="ilListItemSection il_ItemProperties"><span class="il_ItemProperty">pdf</span></div>
     </div></div>
    </div>
   </div>
   <div class="ilCLI ilObjListRow" id="item_row__other-900301">
    <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900301_pref_900101">
     <div class="ilContainerListItemIcon"><img alt="Inline Datei" class="ilListItemIcon" src="./src/FileDelivery/deliver.php/x"/></div>
     <div class="ilContainerListItemContent"><div class="il_ContainerListItem">
      <div class="il_ContainerItemTitle form-inline"><h3 class="il_ContainerItemTitle">
       <a class="il_ContainerItemTitle" href="/ilias.php?baseClass=ilrepositorygui&amp;cmdClass=ilObjFileGUI&amp;cmd=sendfile&amp;ref_id=900301">Skript</a>
       <a class="glyph" href="#"><span class="glyphicon"></span></a>
      </h3></div>
     </div></div>
    </div>
    <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900901_pref_900101">
     <div class="ilContainerListItemIcon"><img alt="Kurslink" class="ilListItemIcon" src="./templates/default/images/standard/icon_crsr.svg"/></div>
     <div class="ilListItemSection il_ItemAlertProperties"><span class="il_ItemAlertProperty">Offline</span></div>
     <div class="ilContainerListItemContent"><div class="il_ContainerListItem">
      <div class="il_ContainerItemTitle form-inline"><h3 class="il_ContainerItemTitle">
       <a class="il_ContainerItemTitle" href="ilias.php?baseClass=ilrepositorygui&amp;ref_id=900102">Kurslink</a>
      </h3></div>
     </div></div>
    </div>
   </div>
  </div>
 </div>
</div></div>
"""


def test_parse_blocks_and_items():
    blocks = parse_container(HTML, "https://ilias.example.org")
    assert [b.name for b in blocks] == ["Objektblock"]
    assert blocks[0].ref_id == 900181
    items = flatten_items(blocks)
    names = [i.name for i in items]
    assert names == ["Klausurordner", "Skript", "Kurslink"]  # Dropdown/Notizen ignoriert
    assert items[0].type == "fold" and items[0].ref_id == 900203
    # Datei-Typ aus dem Link (nicht aus dem "Inline Datei"-Symbol), Display-Duplikate ignoriert
    assert items[1].type == "file" and items[1].ref_id == 900301
    assert items[0].props == ["pdf"]
    # Kurslink behält die eigene ref_id aus data-list-item-id, Typ aus dem Symbol
    assert items[2].type == "crsr" and items[2].ref_id == 900901
    assert items[2].offline is True


def test_structure_and_empty_detection():
    assert has_container_structure(HTML) is True
    assert is_empty_container(HTML) is False
    garbage = "<html><body><h1>Wartungsarbeiten</h1></body></html>"
    assert has_container_structure(garbage) is False
    empty = '<div class="ilContainerBlock" id="bl_cntr_1"><div class="ilNoItems">leer</div></div>'
    assert parse_container(empty, "https://x") == []
    assert is_empty_container(empty) is True
