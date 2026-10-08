"""Fake-ILIAS (HHN, ILIAS 9) mit Kurs- und Ordnerseiten für F2/F3, nur localhost.

Baut auf dem Login-Fake aus tests/acceptance/fake_servers.py auf (Keycloak + TOTP +
ILIAS-Session) und ergänzt die Seiten, die `ilias courses` und `ilias ls` brauchen:

  GET {ilias}/ilias.php?baseClass=ilmembershipoverviewgui      -> "Meine Kurse und Gruppen"
  GET {ilias}/ilias.php?baseClass=ilDashboardGUI[&cmd=...]      -> Dashboard mit derselben Liste
  GET {ilias}/goto.php?target=crs_<ref>|fold_<ref>|grp_<ref>    -> 302 ilias.php?baseClass=ilrepositorygui&ref_id=<ref>
  GET {ilias}/ilias.php?baseClass=ilrepositorygui&ref_id=<ref>  -> Container-Seite (Kurs/Ordner/Gruppe)

ALLE Inhalte sind synthetisch (ausgedachte Kurse/Dateien, keine echten Namen, keine
echten Kursinhalte, keine Matrikelnummern). Das Markup ist nur strukturell an ILIAS 9
angelehnt (Klassen `il-item-title`, `ilContainerListItemOuter`, `il_ContainerItemTitle`,
`il_ItemProperty`, `il_ItemAlertProperty`, `ilContainerBlock`). Die echten Klassen und
URL-Muster an der HHN sind "live zu bestätigen" (docs/HHN_2FA_SPEC.md §9).

Ohne gültige Session leitet jede geschützte Seite auf login.php?cmd=force_login um
(-> Exit 3 im Client).
"""

from __future__ import annotations

import html
import urllib.parse
from dataclasses import dataclass, field

from acceptance.fake_servers import FakeWorld, RecordedRequest, _make_handler

# --------------------------------------------------------------------------- Daten
# Kurse/Gruppen: ref_id -> (Typ, Titel, Beschreibung, Eigenschaften, offline)
MEMBERSHIPS: list[dict] = [
    {"ref_id": 900101, "type": "crs", "title": "Mathematik A für Testzwecke (WiSe 2026/27)",
     "props": {}, "offline": False},
    {"ref_id": 900102, "type": "crs", "title": "Mathematik B für Testzwecke",
     "props": {"Zeitraum": "16. Mär 2026 - 31. Aug 2026"}, "offline": False},
    {"ref_id": 900103, "type": "crs", "title": "Einführung in Fantasieprotokolle",
     "props": {}, "offline": False},
    {"ref_id": 900104, "type": "crs", "title": "Archivkurs Beispielwissen WS 2025/26",
     "props": {}, "offline": True},
    {"ref_id": 900105, "type": "grp", "title": "Lerngruppe Synthese",
     "props": {}, "offline": False},
]

# Erwartete Semester (Spec §5.3)
EXPECTED_SEMESTER = {
    900101: "WiSe 2026/27",  # aus dem Titel
    900102: "SoSe 2026",  # aus der Eigenschaft "Zeitraum" (Start im März)
    900103: None,  # nicht ableitbar
    900104: "WiSe 2025/26",  # aus dem Titel, Kurzform "WS 2025/26"
    900105: None,
}

# Container-Inhalte: ref_id -> Liste von Blöcken (Abschnitten); Block = (Titel, Items)
# Item: dict(type, ref_id, title, props(list[str]), offline, desc)
LONG_TITLE = "Zusammenfassung aller Kapitel mit ausführlichen Beispielen und Lösungswegen Teil 1"
CONTAINERS: dict[int, list[tuple[str, list[dict]]]] = {
    900101: [
        ("Inhalt", [
            {"type": "fold", "ref_id": 900201, "title": "Übungsblätter"},
            {"type": "file", "ref_id": 900301, "title": "Skript Kapitel 1",
             "props": ["pdf", "1,5 MB", "Version: 2", "25. Sep 2026, 10:12"]},
            {"type": "file", "ref_id": 900302, "title": LONG_TITLE,
             "props": ["pdf", "820 KB", "01. Okt 2026, 08:00"]},
            {"type": "webr", "ref_id": 900401, "title": "Übung 3 --> Lösung (Link)"},
            {"type": "exc", "ref_id": 900501, "title": "Hausaufgabe 1"},
            {"type": "tst", "ref_id": 900601, "title": "Selbsttest Kapitel 1"},
            {"type": "frm", "ref_id": 900701, "title": "Forum für Rückfragen"},
            {"type": "xvid", "ref_id": 900801, "title": "Videoplugin-Objekt"},
            {"type": "file", "ref_id": 900303, "title": "Noch nicht freigegeben",
             "props": ["docx", "12 KB"], "offline": True},
        ]),
        ("Klausurvorbereitung", [
            {"type": "fold", "ref_id": 900203, "title": "[Klausur] Altklausuren"},
        ]),
    ],
    900201: [
        ("Inhalt", [
            {"type": "file", "ref_id": 900311, "title": "Blatt 10", "props": ["pdf", "200 KB"]},
            {"type": "file", "ref_id": 900312, "title": "Blatt 2", "props": ["pdf", "180 KB"]},
            {"type": "fold", "ref_id": 900202, "title": "Lösungen"},
        ]),
    ],
    900202: [
        ("Inhalt", [
            {"type": "file", "ref_id": 900321, "title": "Lösung Blatt 2", "props": ["pdf", "2,25 MB"]},
            {"type": "exc", "ref_id": 900521, "title": "Abgabe Lösungen"},
        ]),
    ],
    900203: [
        ("Inhalt", [
            {"type": "file", "ref_id": 900331, "title": "Klausur Beispieljahr", "props": ["pdf", "1 GB"]},
        ]),
    ],
    900102: [("Inhalt", [{"type": "file", "ref_id": 900341, "title": "Organisatorisches", "props": ["pdf", "50 KB"]}])],
    900103: [],  # leerer Kurs
    900104: [("Inhalt", [])],
    900105: [("Inhalt", [{"type": "file", "ref_id": 900351, "title": "Notizen der Gruppe", "props": ["txt", "3 KB"]}])],
}

ICON_ALT = {
    "fold": "Ordner", "file": "Datei", "webr": "Weblink", "exc": "Übung", "tst": "Test",
    "frm": "Forum", "crs": "Kurs", "grp": "Gruppe", "xvid": "Plugin",
}


@dataclass
class HhnWorld(FakeWorld):
    # normal | error503 | garbage | empty
    membership_mode: str = "normal"
    # ref_id -> normal | error500 | garbage | login_redirect
    container_modes: dict[int, str] = field(default_factory=dict)

    def start(self) -> HhnWorld:  # type: ignore[override]
        import threading
        from http.server import ThreadingHTTPServer

        world = self
        base_ilias = _make_handler(self, "ilias")
        base_kc = _make_handler(self, "keycloak")

        class IliasHandler(base_ilias):  # type: ignore[misc,valid-type]
            def _ilias(self, rec: RecordedRequest):
                if not world.handle_repo(self, rec):
                    super()._ilias(rec)

        ilias = ThreadingHTTPServer(("127.0.0.1", 0), IliasHandler)
        kc = ThreadingHTTPServer(("127.0.0.1", 0), base_kc)
        self.ilias_port = ilias.server_address[1]
        self.kc_port = kc.server_address[1]
        for srv in (ilias, kc):
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._servers.append(srv)
        return self

    # ---------------------------------------------------------------- Routing
    def _login_redirect(self, handler, target: str = "") -> None:
        handler._redirect(
            f"{self.ilias_base}/login.php?target={urllib.parse.quote(target)}"
            f"&client_id={self.ilias_client_id}&cmd=force_login&lang=de"
        )

    def handle_repo(self, handler, rec: RecordedRequest) -> bool:
        path = rec.path
        if self.ilias_prefix:
            if not path.startswith(self.ilias_prefix + "/"):
                return False
            path = path[len(self.ilias_prefix):]
        q = {k: v[0] for k, v in rec.query.items()}
        sid = rec.cookies.get("PHPSESSID")
        with self.lock:
            valid = sid in self.valid_sessions

        if path == "/goto.php":
            target = q.get("target", "")
            parts = target.split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                if not valid:
                    self._login_redirect(handler, target)
                    return True
                handler._redirect(f"{self.ilias_base}/ilias.php?baseClass=ilrepositorygui&ref_id={parts[1]}")
                return True
            return False

        if path != "/ilias.php":
            return False
        base_class = q.get("baseClass", "").lower()
        if base_class == "ildashboardgui" and q.get("cmd") in (None, "", "jumpToSelectedItems", "jumpToMemberships", "show"):
            if not valid:
                self._login_redirect(handler)
                return True
            if self.dashboard_mode == "error503":
                return False  # Basis-Fake liefert 503
            handler._send(200, self.page("Dashboard", self.membership_html()))
            return True
        if base_class == "ilmembershipoverviewgui":
            if not valid:
                self._login_redirect(handler)
                return True
            if self.membership_mode == "error503":
                handler._send(503, "<h1>503 Service Temporarily Unavailable</h1><hr><center>nginx</center>")
            elif self.membership_mode == "garbage":
                handler._send(200, "<!DOCTYPE html><html><body><h1>Wartungsarbeiten</h1></body></html>")
            else:
                handler._send(200, self.page("Meine Kurse und Gruppen", self.membership_html()))
            return True
        if base_class == "ilrepositorygui" and q.get("ref_id", "").isdigit():
            ref = int(q["ref_id"])
            if not valid:
                self._login_redirect(handler, f"crs_{ref}")
                return True
            mode = self.container_modes.get(ref, "normal")
            if mode == "login_redirect":
                self._login_redirect(handler, f"fold_{ref}")
            elif mode == "error500":
                handler._send(500, "<h1>500 Internal Server Error</h1>")
            elif mode == "garbage":
                handler._send(200, "<!DOCTYPE html><html><body><p>Unerwartete Seite</p></body></html>")
            elif ref not in CONTAINERS:
                handler._send(200, self.page("Fehler", '<div class="alert alert-danger" role="alert">'
                                              'Sie haben nicht die notwendige Berechtigung.</div>'))
            else:
                title = self.title_of(ref)
                handler._send(200, self.page(title, self.container_html(ref)))
            return True
        return False

    # ---------------------------------------------------------------- HTML
    @staticmethod
    def title_of(ref: int) -> str:
        for m in MEMBERSHIPS:
            if m["ref_id"] == ref:
                return m["title"]
        for blocks in CONTAINERS.values():
            for _, items in blocks:
                for it in items:
                    if it["ref_id"] == ref:
                        return it["title"]
        return "?"

    def page(self, title: str, content: str) -> str:
        p = self.ilias_prefix
        t = html.escape(title)
        return f"""<!DOCTYPE html>
<html lang="de" dir="ltr">
<head><meta charset="UTF-8"><title>{t}: HHN ILIAS</title></head>
<body class="std"><div class="il-layout-page">
 <header class="il-header"><div class="header-inner"><div class="il-pagetitle">{t}</div>
  <ul class="il-maincontrols-metabar" role="menubar"><li role="none">
   <ul class="il-maincontrols-slate"><li><a href="{p}/logout.php?lang=de">Abmelden</a></li></ul></li></ul>
 </div></header>
 <main class="il-layout-page-content"><div id="mainspacekeeper">
  <div class="il_HeaderInner"><h1 class="il_ContainerTitle">{t}</h1></div>
{content}
 </div></main>
 <footer class="il-footer">ILIAS v9.24 (2026-10-06)</footer>
</div></body></html>"""

    def membership_html(self) -> str:
        if self.membership_mode == "empty":
            return '<div class="il-item-group"><div class="ilNoItems">Sie sind noch keinem Kurs und keiner Gruppe beigetreten.</div></div>'
        out = []
        for kind, label in (("crs", "Kurse"), ("grp", "Gruppen")):
            items = []
            for m in MEMBERSHIPS:
                if m["type"] != kind:
                    continue
                props = "".join(
                    f'<div class="col-md-6"><span class="il-item-property-name">{html.escape(k)}</span>'
                    f'<span class="il-item-property-value">{html.escape(v)}</span></div>'
                    for k, v in m["props"].items()
                )
                if m["offline"]:
                    props += ('<div class="col-md-6"><span class="il-item-property-name">Status</span>'
                              '<span class="il-item-property-value il-item-property-alert">Offline</span></div>')
                href = f"./goto.php?target={kind}_{m['ref_id']}&amp;client_id={self.ilias_client_id}"
                items.append(f"""<li class="il-std-item-container"><div class="il-item il-std-item">
  <div class="row"><div class="col-sm-1"><img class="icon {kind} medium" src="./templates/default/images/standard/icon_{kind}.svg" alt="{ICON_ALT[kind]}"/></div>
  <div class="col-sm-11"><h4 class="il-item-title"><a href="{href}">{html.escape(m['title'])}</a></h4>
   <div class="il-item-description">Synthetischer Beispielkurs</div>
   <hr class="il-item-divider" /><div class="row il-item-properties">{props}</div>
   <div class="dropdown"><ul class="dropdown-menu"><li><a href="{href}">Öffnen</a></li><li><a href="#">Kurs verlassen</a></li></ul></div>
  </div></div></div></li>""")
            out.append(f'<div class="il-item-group"><h3>{label}</h3><div class="il-item-group-items"><ul>{"".join(items)}</ul></div></div>')
        return "\n".join(out)

    def item_href(self, it: dict) -> str:
        t, ref = it["type"], it["ref_id"]
        if t == "file":
            return f"./goto.php?target=file_{ref}_download&amp;client_id={self.ilias_client_id}"
        if t == "webr":
            return f"./ilias.php?baseClass=ilLinkResourceHandlerGUI&amp;ref_id={ref}&amp;cmd=calldirectlink"
        if t == "fold":
            return f"./ilias.php?baseClass=ilrepositorygui&amp;ref_id={ref}"
        return f"./goto.php?target={t}_{ref}&amp;client_id={self.ilias_client_id}"

    def container_html(self, ref: int) -> str:
        blocks = CONTAINERS[ref]
        if not blocks:
            return '<div class="ilContainerBlock"><div class="ilNoItems">Dieser Kurs enthält keine Objekte.</div></div>'
        out = []
        for i, (block_title, items) in enumerate(blocks, start=1):
            rows = []
            for it in items:
                href = self.item_href(it)
                props = "".join(f'<span class="il_ItemProperty">{html.escape(p)}&nbsp;&nbsp;</span>' for p in it.get("props", []))
                alert = '<div class="ilListItemSection il_ItemAlertProperties"><span class="il_ItemAlertProperty">Offline</span></div>' if it.get("offline") else ""
                rows.append(f"""<div class="ilContainerListItemOuter" id="lg_div_{it['ref_id']}_pref_{ref}">
 <div class="ilContainerListItemContent">
  <div class="ilContainerListItemIcon"><img src="./templates/default/images/standard/icon_{it['type']}.svg" class="ilListItemIcon" alt="Symbol {ICON_ALT.get(it['type'], 'Objekt')}" title="Symbol {ICON_ALT.get(it['type'], 'Objekt')}"/></div>
  <div class="ilContainerListItemContentCB"><div class="il_ContainerListItem">
   <h3 class="il_ContainerItemTitle"><a href="{href}" class="il_ContainerItemTitle">{html.escape(it['title'])}</a></h3>
   <div class="ilListItemSection il_Description">Synthetische Beschreibung</div>
   <div class="ilListItemSection il_ItemProperties">{props}</div>
   {alert}
  </div></div>
  <div class="ilContainerListItemCommands"><div class="dropdown"><ul class="dropdown-menu">
   <li><a href="{href}">{html.escape(it['title'])}</a></li><li><a href="#">Link</a></li></ul></div></div>
 </div></div>""")
            if not rows:
                rows.append('<div class="ilNoItems">Keine Objekte</div>')
            out.append(f"""<div class="ilContainerBlock container-fluid" id="bl_cntr_{i}">
 <div class="ilContainerBlockHeader"><h2 class="ilContainerBlockHeaderTitle">{html.escape(block_title)}</h2></div>
 <div class="ilContainerItemsContainer">{''.join(rows)}</div></div>""")
        return "\n".join(out)
