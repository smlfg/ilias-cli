"""Unit-Tests für ilias_core.ilias_html.membership (Spec §5, §13.2)."""

from __future__ import annotations

import pytest

from ilias_core.ilias_html.membership import (
    parse_memberships,
    extract_semester_from_title,
    extract_semester_from_period,
    normalize_text,
)


class TestNormalizeText:
    """Text-Normalisierung: Entities, NFC, Whitespace."""

    def test_entities(self):
        assert normalize_text("Test & Beispiel") == "Test & Beispiel"
        assert normalize_text("A&nbsp;B") == "A B"
        assert normalize_text("A>B") == "A>B"

    def test_nfc(self):
        # NFD -> NFC
        nfd = "L\u00f6sung"  # "Lösung" in NFD
        assert normalize_text(nfd) == "Lösung"

    def test_whitespace(self):
        assert normalize_text("  A   B  \n  C  ") == "A B C"
        assert normalize_text("\t\n") == ""


class TestSemesterExtraction:
    """Semester-Erkennung aus Titel (Spec §5.3, §13.11)."""

    @pytest.mark.parametrize("title,expected", [
        ("Mathematik A (WiSe 2026/27)", "WiSe 2026/27"),
        ("Mathematik B (WS 2025/26)", "WiSe 2025/26"),
        ("Wintersemester 2024/25", "WiSe 2024/25"),
        ("WiSe26/27 Test", "WiSe 2026/27"),
        ("_WS26_27 Test", "WiSe 2026/27"),
        ("2026 WS Test", "WiSe 2026/27"),
        ("Test 2026 WS", "WiSe 2026/27"),
        ("SoSe 2026 Test", "SoSe 2026"),
        ("SS 2026 Test", "SoSe 2026"),
        ("SS26 Test", "SoSe 2026"),
        ("Sommersemester 2026", "SoSe 2026"),
        ("SoSe26 Test", "SoSe 2026"),
        ("_SS26 Test", "SoSe 2026"),
        ("2026 SS Test", "SoSe 2026"),
        ("Kein Semester hier", None),
    ])
    def test_extract_from_title(self, title: str, expected: str | None):
        assert extract_semester_from_title(title) == expected

    def test_extract_from_period(self):
        """Zeitraum-Eigenschaft: März-August -> SoSe, Sep-Feb -> WiSe."""
        # Start im März -> SoSe
        assert extract_semester_from_period("Zeitraum: 16. Mär 2026 - 31. Aug 2026") == "SoSe 2026"
        # Start im September -> WiSe
        assert extract_semester_from_period("16. Sep 2026 - 31. Jan 2027") == "WiSe 2026/27"
        # Start im Januar -> WiSe Vorjahr
        assert extract_semester_from_period("16. Jan 2027 - 31. Jul 2027") == "WiSe 2026/27"
        # Start im Februar -> WiSe Vorjahr
        assert extract_semester_from_period("16. Feb 2027 - 31. Jul 2027") == "WiSe 2026/27"
        # Ungültig
        assert extract_semester_from_period("kein Zeitraum") is None


class TestParseMemberships:
    """Parser für 'Meine Kurse und Gruppen'."""

    def test_parse_basic(self):
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div class="panel-body">
            <div class="il-item-group">
              <h3>Fachgruppe Test</h3>
              <div class="il-item-group-items">
                <ul>
                  <li class="il-std-item-container">
                    <div class="il-item il-std-item">
                      <div class="media">
                        <div class="media-left"><img alt="Kurs" class="icon custom medium" src="/icon_crs.svg"/></div>
                        <div class="media-body">
                          <h4 class="il-item-title"><a href="https://ilias.example.org/go/crs/900101">Mathematik A (WiSe 2026/27)</a></h4>
                          <div class="il-item-description">Beschreibung</div>
                        </div>
                      </div>
                    </div>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        memberships = parse_memberships(html, "https://ilias.example.org")
        assert len(memberships) == 1
        m = memberships[0]
        assert m.ref_id == 900101
        assert m.type == "crs"
        assert m.title == "Mathematik A (WiSe 2026/27)"
        assert m.description == "Beschreibung"
        assert m.visible is True
        assert m.semester == "WiSe 2026/27"
        assert m.url == "https://ilias.example.org/go/crs/900101"

    def test_parse_group(self):
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div class="panel-body">
            <div class="il-item-group">
              <div class="il-item-group-items">
                <ul>
                  <li class="il-std-item-container">
                    <div class="il-item il-std-item">
                      <div class="media">
                        <div class="media-left"><img alt="Gruppe" class="icon custom medium" src="/icon_grp.svg"/></div>
                        <div class="media-body">
                          <h4 class="il-item-title"><a href="https://ilias.example.org/go/grp/900105">Lerngruppe</a></h4>
                        </div>
                      </div>
                    </div>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        memberships = parse_memberships(html, "https://ilias.example.org")
        assert len(memberships) == 1
        m = memberships[0]
        assert m.type == "grp"
        assert m.ref_id == 900105

    def test_parse_offline(self):
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div class="panel-body">
            <div class="il-item-group">
              <div class="il-item-group-items">
                <ul>
                  <li class="il-std-item-container">
                    <div class="il-item il-std-item">
                      <div class="media">
                        <div class="media-body">
                          <h4 class="il-item-title"><a href="https://ilias.example.org/go/crs/900104">Archivkurs</a></h4>
                          <hr class="il-item-divider"/>
                          <div class="row il-item-properties">
                            <div class="col-md-6 il-multi-line-cap-3">
                              <span class="il-item-property-name">Status</span>
                              <span class="il-item-property-value">Offline</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        memberships = parse_memberships(html, "https://ilias.example.org")
        assert len(memberships) == 1
        assert memberships[0].visible is False

    def test_parse_period_property(self):
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div class="panel-body">
            <div class="il-item-group">
              <div class="il-item-group-items">
                <ul>
                  <li class="il-std-item-container">
                    <div class="il-item il-std-item">
                      <div class="media">
                        <div class="media-body">
                          <h4 class="il-item-title"><a href="https://ilias.example.org/go/crs/900102">Mathematik B</a></h4>
                          <hr class="il-item-divider"/>
                          <div class="row il-item-properties">
                            <div class="col-md-6 il-multi-line-cap-3">
                              <span class="il-item-property-name">Zeitraum</span>
                              <span class="il-item-property-value">16. Mär 2026 - 31. Aug 2026</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        </body></html>
        """
        memberships = parse_memberships(html, "https://ilias.example.org")
        assert len(memberships) == 1
        # Zeitraum Start im März -> SoSe
        assert memberships[0].semester == "SoSe 2026"

    def test_parse_empty(self):
        """Leere Liste -> leere Liste, kein Fehler."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div class="panel-body">
            <div class="alert alert-info">Sie sind noch keinem Kurs und keiner Gruppe beigetreten.</div>
          </div>
        </div>
        </body></html>
        """
        memberships = parse_memberships(html, "https://ilias.example.org")
        assert memberships == []

    def test_ignore_metabar_notifications(self):
        """Benachrichtigungen in der Metabar dürfen nicht als Kurse geparst werden."""
        html = """
        <html><body>
        <div id="ilContentContainer">
          <div class="panel-body">
            <div class="il-item-group">
              <div class="il-item-group-items">
                <ul>
                  <li class="il-std-item-container">
                    <div class="il-item il-std-item">
                      <div class="media">
                        <div class="media-body">
                          <h4 class="il-item-title"><a href="https://ilias.example.org/go/crs/900101">Echter Kurs</a></h4>
                        </div>
                      </div>
                    </div>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        <!-- Metabar mit Benachrichtigung (außerhalb von #ilContentContainer .panel-body) -->
        <ul class="il-maincontrols-metabar">
          <li>
            <div class="il-item-notification-replacement-container">
              <div class="il-item il-notification-item">
                <div class="media">
                  <div class="media-body">
                    <h4 class="il-item-notification-title">Benachrichtigung</h4>
                    <div class="row il-item-properties">
                      <div class="col-sm-12 il-multi-line-cap-3">
                        <span class="il-item-property-name">Zeit</span>
                        <span class="il-item-property-value">6. Okt 2026, 14:20</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </li>
        </ul>
        </body></html>
        """
        memberships = parse_memberships(html, "https://ilias.example.org")
        # Nur der echte Kurs im Hauptinhalt
        assert len(memberships) == 1
        assert memberships[0].title == "Echter Kurs"