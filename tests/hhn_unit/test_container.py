"""Unit-Tests für ilias_core.ilias_html.container (Spec §6, §13.3)."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from ilias_core.ilias_html.container import (
    parse_container,
    parse_container_item,
    item_to_module,
    normalize_text,
    guess_type_from_icon,
)
from ilias_core.ilias_html.links import parse_link_from_item


class TestNormalizeText:
    """Text-Normalisierung für Container-Items."""

    def test_basic(self):
        assert normalize_text("  Test  ") == "Test"
        assert normalize_text("A&nbsp;B") == "A B"
        assert normalize_text("A>B") == "A>B"
        assert normalize_text("Lösung") == "Lösung"  # NFC

    def test_never_truncate(self):
        long = "x" * 1000
        assert normalize_text(long) == long


class TestGuessTypeFromIcon:
    """Typ-Raten aus Icon (Fallback)."""

    @pytest.mark.parametrize("alt,expected", [
        ("Ordner", "fold"),
        ("Datei", "file"),
        ("Inline Datei", "file"),
        ("Weblink", "webr"),
        ("Übung", "exc"),
        ("Test", "tst"),
        ("Forum", "frm"),
        ("Sitzung", "sess"),
        ("Objektblock", "itgr"),
        ("Kurslink", "crsr"),
        ("Gruppe", "grp"),
        ("Kategorie", "cat"),
        ("Unbekannt", None),
    ])
    def test_icon_mapping(self, alt: str, expected: str | None):
        assert guess_type_from_icon(alt, None) == expected


class TestParseContainer:
    """Container-Seite parsen (Legacy-Liste: ilContainerBlock -> Abschnitte)."""

    def test_parse_basic_course(self):
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerBlockHeader">
                <h2 class="ilHeader ilContainerBlockHeader">Inhalt</h2>
              </div>
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900201">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900201_pref_900101" id="lg_div_900201_pref_900101">
                    <div class="ilContainerListItemIcon">
                      <img alt="Ordner" class="ilListItemIcon" src="/icon_fold.svg" title="Ordner"/>
                    </div>
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="https://ilias.example.org/go/fold/900201">Übungsblätter</a>
                          </h3>
                        </div>
                        <div class="ilFloatRight"></div>
                        <div class="ilListItemSection il_Description"></div>
                        <div class="ilListItemSection il_ItemProperties">
                          <span class="il_ItemProperty">pdf</span>
                          <span class="il_ItemProperty">1.5 MB</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        assert len(blocks) == 1
        assert blocks[0].title == "Inhalt"
        assert len(blocks[0].items) == 1
        item = blocks[0].items[0]
        assert item.ref_id == 900201
        assert item.type == "fold"
        assert item.title == "Übungsblätter"

    def test_parse_object_block_itgr(self):
        """Objektblock (itgr) mit data-store-url."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" data-behaviour="0" data-store-url="./ilias.php?baseClass=ilcontainerblockpropertiesstoragegui&cmd=store&cont_block_id=itgr_900181" id="bl_cntr_1">
              <div class="ilContainerBlockHeader">
                <h2 class="ilHeader ilContainerBlockHeader">Klausurvorbereitung</h2>
              </div>
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row_itgr_900181-900203">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900203_pref_900101" id="lg_div_900203_pref_900101">
                    <div class="ilContainerListItemIcon">
                      <img alt="Ordner" class="ilListItemIcon" src="/icon_fold.svg" title="Ordner"/>
                    </div>
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="https://ilias.example.org/go/fold/900203">[Klausur] Altklausuren</a>
                          </h3>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        assert len(blocks) == 1
        assert blocks[0].title == "Klausurvorbereitung"
        assert blocks[0].itgr_ref_id == 900181

    def test_parse_file_with_inline_icon(self):
        """Datei mit eigenem Symbol (deliver.php, alt='Inline Datei')."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900301">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900301_pref_900101" id="lg_div_900301_pref_900101">
                    <div class="ilContainerListItemIcon">
                      <img alt="Inline Datei" class="ilListItemIcon" src="https://ilias.example.org/src/FileDelivery/deliver.php/beispiel-symbol-900301" title="Inline Datei"/>
                    </div>
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=900301" target="_blank">Skript Kapitel 1</a>
                            <span></span><a aria-label="Vorschau" class="glyph" href="#" tabindex="0"><span class="glyphicon glyphicon-eye-open"></span></a>
                          </h3>
                        </div>
                        <div class="ilListItemSection il_ItemProperties">
                          <span class="il_ItemProperty">pdf</span>
                          <span class="il_ItemProperty">1.5 MB</span>
                          <span class="il_ItemProperty">25. Sep 2026, 10:12</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        item = blocks[0].items[0]
        assert item.ref_id == 900301
        assert item.type == "file"
        assert item.inline is True
        assert "pdf" in item.props
        assert "1.5 MB" in item.props

    def test_parse_webr(self):
        """Weblink."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900401">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900401_pref_900101" id="lg_div_900401_pref_900101">
                    <div class="ilContainerListItemIcon">
                      <img alt="Weblink" class="ilListItemIcon" src="/icon_webr.svg" title="Weblink"/>
                    </div>
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=900401&cmd=calldirectlink" target="_blank">Übung 3 --> Lösung (Link)</a>
                          </h3>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        item = blocks[0].items[0]
        assert item.ref_id == 900401
        assert item.type == "webr"

    def test_parse_crsr(self):
        """Kurslink (crsr) behält eigene ref_id aus data-list-item-id."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900901">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900901_pref_900101" id="lg_div_900901_pref_900101">
                    <div class="ilContainerListItemIcon">
                      <img alt="Kurslink" class="ilListItemIcon" src="/icon_crsr.svg" title="Kurslink"/>
                    </div>
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="ilias.php?baseClass=ilrepositorygui&ref_id=900102" target="_top">Verknüpfung Mathematik-Zusatz</a>
                          </h3>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        item = blocks[0].items[0]
        assert item.ref_id == 900901  # aus data-list-item-id
        assert item.type == "crsr"
        assert item.target_ref_id == 900102  # Ziel-Kurs aus Link

    def test_parse_session(self):
        """Sitzung (sess) mit Expand-Link -> children=None."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900971">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900971_pref_900101" id="lg_div_900971_pref_900101">
                    <div class="ilContainerListItemIcon">
                      <img alt="Sitzung" class="ilListItemIcon" src="/icon_sess.svg" title="Sitzung"/>
                    </div>
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="https://ilias.example.org/go/sess/900971">Sitzung 1: Auftakt</a>
                          </h3>
                        </div>
                        <div class="ilListItemSection">
                          <a href="ilias.php?baseClass=ilrepositorygui&ref_id=900101&expand=900971">
                            <span class="glyphicon glyphicon-triangle-right"></span>
                          </a>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        item = blocks[0].items[0]
        assert item.ref_id == 900971
        assert item.type == "sess"

    def test_parse_offline_item(self):
        """Offline-Objekt -> visible=False."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900303">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900303_pref_900101" id="lg_div_900303_pref_900101">
                    <div class="ilContainerListItemIcon">
                      <img alt="Datei" class="ilListItemIcon" src="/icon_file.svg" title="Datei"/>
                    </div>
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="https://ilias.example.org/go/file/900303">Noch nicht freigegeben</a>
                          </h3>
                        </div>
                        <div class="ilListItemSection il_ItemAlertProperties">
                          <span class="il_ItemAlertProperty">Offline</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        item = blocks[0].items[0]
        assert item.visible is False

    def test_ignore_dropdown_links(self):
        """Dropdown/Aktions-Links (href='#', .glyph) werden ignoriert, kein doppelter Eintrag."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900201">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900201_pref_900101" id="lg_div_900201_pref_900101">
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="https://ilias.example.org/go/fold/900201">Übungsblätter</a>
                            <a class="glyph" href="#">Vorschau</a>
                          </h3>
                        </div>
                        <div class="ilFloatRight">
                          <div class="btn-group">
                            <ul class="dropdown-menu">
                              <li><a href="#" role="menuitem">Download</a></li>
                              <li><a href="#" role="menuitem">Info</a></li>
                            </ul>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        # Nur EIN Eintrag pro ref_id
        assert len(blocks[0].items) == 1
        assert blocks[0].items[0].title == "Übungsblätter"

    def test_duplicate_div_h3_title(self):
        """il_ContainerItemTitle auf div UND h3 -> Titel nur aus a.il_ContainerItemTitle."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div id="il_center_col">
            <div class="ilContainerBlock form-inline" id="bl_cntr_1">
              <div class="ilContainerItemsContainer">
                <div class="ilCLI ilObjListRow" id="item_row__other-900201">
                  <div class="ilContainerListItemOuter" data-list-item-id="lg_div_900201_pref_900101" id="lg_div_900201_pref_900101">
                    <div class="ilContainerListItemContent">
                      <div class="il_ContainerListItem">
                        <div class="il_ContainerItemTitle form-inline">
                          <h3 class="il_ContainerItemTitle">
                            <a class="il_ContainerItemTitle" href="https://ilias.example.org/go/fold/900201">Richtiger Titel</a>
                          </h3>
                          <div class="il_ContainerItemTitle">Falscher Titel aus div</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        blocks = parse_container(html, "https://ilias.example.org", 900101)
        assert blocks[0].items[0].title == "Richtiger Titel"


class TestItemToModule:
    """ContainerItem in Modul-Dict für JSON umwandeln."""

    def test_fold_to_module(self):
        from ilias_core.ilias_html.container import ContainerItem
        item = ContainerItem(
            ref_id=900201,
            type="fold",
            title="Übungsblätter",
            url="https://ilias.example.org/go/fold/900201",
            visible=True,
            props=[],
            inline=False,
            target_ref_id=None,
            icon_alt="Ordner",
        )
        module = item_to_module(item, "https://ilias.example.org", "/")
        assert module["type"] == "folder"
        assert module["modname"] == "fold"
        assert module["name"] == "Übungsblätter"
        assert module["path"] == "/Übungsblätter/"
        assert module["children"] == []

    def test_file_to_module(self):
        from ilias_core.ilias_html.container import ContainerItem
        item = ContainerItem(
            ref_id=900301,
            type="file",
            title="Skript.pdf",
            url="https://ilias.example.org/ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=900301",
            visible=True,
            props=["pdf", "1.5 MB", "25. Sep 2026, 10:12"],
            inline=False,
            target_ref_id=None,
            icon_alt="Datei",
        )
        module = item_to_module(item, "https://ilias.example.org", "/")
        assert module["type"] == "file"
        assert module["modname"] == "file"
        assert module["size"] is not None
        assert module["size_text"] == "1.5 MB"
        assert module["suffix"] == "pdf"
        assert module["timemodified"] is not None
        assert "cmd=sendfile" in module["fileurl"]

    def test_webr_to_module(self):
        from ilias_core.ilias_html.container import ContainerItem
        item = ContainerItem(
            ref_id=900401,
            type="webr",
            title="Externer Link",
            url="https://ilias.example.org/ilias.php?baseClass=ilLinkResourceHandlerGUI&ref_id=900401&cmd=calldirectlink",
            visible=True,
            props=[],
            inline=False,
            target_ref_id=None,
            icon_alt="Weblink",
        )
        module = item_to_module(item, "https://ilias.example.org", "/")
        assert module["type"] == "url"
        assert module["modname"] == "webr"
        assert module["target_url"] is None

    def test_sess_to_module(self):
        from ilias_core.ilias_html.container import ContainerItem
        item = ContainerItem(
            ref_id=900971,
            type="sess",
            title="Sitzung 1",
            url="https://ilias.example.org/go/sess/900971",
            visible=True,
            props=[],
            inline=False,
            target_ref_id=None,
            icon_alt="Sitzung",
        )
        module = item_to_module(item, "https://ilias.example.org", "/")
        assert module["type"] == "session"
        assert module["modname"] == "sess"
        assert module["children"] is None

    def test_grp_to_module(self):
        from ilias_core.ilias_html.container import ContainerItem
        item = ContainerItem(
            ref_id=900105,
            type="grp",
            title="Gruppe",
            url="https://ilias.example.org/go/grp/900105",
            visible=True,
            props=[],
            inline=False,
            target_ref_id=None,
            icon_alt="Gruppe",
        )
        module = item_to_module(item, "https://ilias.example.org", "/")
        assert module["type"] == "folder"
        assert module["modname"] == "grp"
        assert module["path"] == "/Gruppe/"