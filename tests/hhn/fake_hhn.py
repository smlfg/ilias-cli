"""Fake-ILIAS (HHN, ILIAS 9.24) mit Kurs- und Ordnerseiten für F2/F3, nur localhost.

Baut auf dem Login-Fake aus tests/acceptance/fake_servers.py auf (Keycloak + TOTP +
ILIAS-Session) und ergänzt die Seiten, die `ilias courses` und `ilias ls` brauchen:

  GET {ilias}/ilias.php?baseClass=ilmembershipoverviewgui      -> "Meine Kurse und Gruppen" (einzige Kursquelle)
  GET {ilias}/ilias.php?baseClass=ilDashboardGUI[&cmd=...]      -> Dashboard, nur Favoriten (Teilmenge!)
  GET {ilias}/go/<typ>/<ref>                                    -> 302 ilias.php?baseClass=ilrepositorygui&ref_id=<ref>
  GET {ilias}/goto.php?target=<typ>_<ref>                       -> dito; unbekannte ref -> 302 Dashboard
  GET {ilias}/ilias.php?baseClass=ilrepositorygui&ref_id=<ref>  -> Container-Seite (Kurs/Ordner/Gruppe);
                                                                   unbekannte/verbotene ref -> 302 ref_id=1
  GET {ilias}/ilias.php?baseClass=ilrepositorygui&ref_id=1      -> Magazin-Wurzel: Fehler-Alert + Kategorien

Strukturtreue (Live-Befund 08.10., docs/HHN_2FA_SPEC.md §13): Tags, Klassen, ids und
data-Attribute folgen den echten HHN-Seiten. ALLE Inhalte sind ausgedacht: Titel, Dateinamen,
Beschreibungen, Daten, ref_ids (>= 900101), Kursnummern. Keine echten Namen, keine echten
URLs (außer dem Muster der Pfade), keine Tokens. Rohes HTML der HHN liegt nie im Repo.

Ohne gültige Session leitet jede geschützte Seite auf login.php?cmd=force_login um
(-> Exit 3 im Client).
"""

from __future__ import annotations

import html
import itertools
import re
import urllib.parse
from dataclasses import dataclass, field

from acceptance.fake_servers import FakeWorld, RecordedRequest, _make_handler

from .fixtures.courses.data import (  # noqa: F401  (Re-Export für Tests)
    COURSE_NUMBERS,
    EXPECTED_SEMESTER,
    FAVORITES,
    MEMBERSHIPS,
)
from .fixtures.ls.data import (  # noqa: F401  (Re-Export für Tests)
    CHAIN_START,
    CONTAINERS,
    LONG_TITLE,
    NFC_TITLE,
    NFD_TITLE,
    ROOT_CATEGORIES,
)

ICON_ALT = {
    "fold": "Ordner", "file": "Datei", "webr": "Weblink", "exc": "Übung", "tst": "Test",
    "frm": "Forum", "crs": "Kurs", "grp": "Gruppe", "xvid": "Plugin", "wiki": "Wiki",
    "crsr": "Kurslink", "sess": "Sitzung", "cat": "Kategorie",
}


def _e(text: str) -> str:
    return html.escape(text, quote=True)


@dataclass
class HhnWorld(FakeWorld):
    # normal | error503 | garbage | empty
    membership_mode: str = "normal"
    # ref_id -> normal | error500 | garbage | login_redirect | forbidden | public_view
    container_modes: dict[int, str] = field(default_factory=dict)
    # ref_id -> zusätzliche Items im letzten Block (z. B. Zyklus 900202 -> 900201)
    extra_items: dict[int, list[dict]] = field(default_factory=dict)
    # Startkurs 900101 bekommt einen Ordner in einen endlosen Ordner-Kanal (Crawl-Limit-Test)
    endless_chain: bool = False
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

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

    # ---------------------------------------------------------------- Helfer für Tests
    def requested_refs(self, since: int = 0) -> list[int]:
        """ref_ids aller ILIAS-GETs ab Index `since` (Query ref_id, /go/<t>/<ref>, goto.php?target=<t>_<ref>)."""
        out = []
        for r in self.requests[since:]:
            if r.server != "ilias" or r.method != "GET":
                continue
            ref = r.query.get("ref_id", [""])[0]
            m = re.search(r"/go/[a-z]+/(\d+)", r.path)
            t = re.match(r"[a-z]+_(\d+)", r.query.get("target", [""])[0])
            for v in (ref, m.group(1) if m else "", t.group(1) if t else ""):
                if v.isdigit():
                    out.append(int(v))
        return out

    # ---------------------------------------------------------------- Routing
    def _login_redirect(self, handler, target: str = "") -> None:
        handler._redirect(
            f"{self.ilias_base}/login.php?target={urllib.parse.quote(target)}"
            f"&client_id={self.ilias_client_id}&cmd=force_login&lang=de"
        )

    def _known_container(self, ref: int) -> bool:
        if ref in CONTAINERS:
            return True
        return self.endless_chain and ref >= CHAIN_START

    def _repo_url(self, ref: int) -> str:
        return f"{self.ilias_base}/ilias.php?baseClass=ilrepositorygui&ref_id={ref}"

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

        m = re.fullmatch(r"/go/([a-z]+)/(\d+)", path)
        if m:
            if not valid:
                self._login_redirect(handler, f"{m.group(1)}_{m.group(2)}")
                return True
            handler._redirect(self._repo_url(int(m.group(2))))
            return True

        if path == "/goto.php":
            parts = q.get("target", "").split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                if not valid:
                    self._login_redirect(handler, q.get("target", ""))
                    return True
                ref = int(parts[1])
                if self._known_container(ref) or ref in {mm["ref_id"] for mm in MEMBERSHIPS}:
                    handler._redirect(self._repo_url(ref))
                else:  # HHN: unbekannte ref -> Dashboard
                    handler._redirect(f"{self.ilias_base}/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems")
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
            handler._send(200, self.page("Dashboard", self.dashboard_html()))
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
            if ref == 1:
                handler._send(200, self.page("Magazin", self.root_html(), alert=self.permission_alert()))
                return True
            mode = self.container_modes.get(ref, "normal")
            if mode == "login_redirect":
                self._login_redirect(handler, f"fold_{ref}")
            elif mode == "error500":
                handler._send(500, "<h1>500 Internal Server Error</h1>")
            elif mode == "garbage":
                handler._send(200, "<!DOCTYPE html><html><body><p>Unerwartete Seite</p></body></html>")
            elif mode == "public_view":
                # 200, aber öffentliche Ansicht: Metabar mit Anmelde-Link statt Abmelden, Kategorien
                handler._send(200, self.page("Magazin", self.root_html(), logged_in=False))
            elif mode == "forbidden" or not self._known_container(ref):
                # HHN: keine Berechtigung/unbekannte ref -> 302 auf die Wurzel mit Fehler-Alert + Kategorien
                handler._redirect(self._repo_url(1))
            else:
                handler._send(200, self.page(self.title_of(ref), self.container_html(ref), tabs=ref))
            return True
        return False

    # ---------------------------------------------------------------- HTML
    @staticmethod
    def title_of(ref: int) -> str:
        for mm in MEMBERSHIPS:
            if mm["ref_id"] == ref:
                return mm["title"]
        for blocks in CONTAINERS.values():
            for _, _, items in blocks:
                for it in items:
                    if it["ref_id"] == ref:
                        return it["title"]
        if ref >= CHAIN_START:
            return f"Kanal-Ordner {ref - CHAIN_START}"
        return "?"

    def _uid(self) -> str:
        return f"il_ui_fw_testid{next(self._ids):05d}"

    def metabar(self, logged_in: bool) -> str:
        b = self.ilias_base
        if not logged_in:
            return (f'<ul class="il-maincontrols-metabar" role="menubar"><li role="none">'
                    f'<a class="btn btn-bulky" href="{b}/login.php?target=root_1&amp;client_id={self.ilias_client_id}'
                    f'&amp;cmd=force_login&amp;lang=de"><span class="bulky-label">Anmelden</span></a></li></ul>')
        # Benachrichtigung im Metabar: ein il-item MIT Eigenschaft "Zeit" -> nie als Kurs/Semester lesen
        return f"""<ul class="il-maincontrols-metabar" role="menubar">
  <li role="none"><div class="il-maincontrols-slate il-maincontrols-slate-notification"><div class="il-maincontrols-slate-content">
   <div class="il-item-notification-replacement-container"><div class="il-item il-notification-item"><div class="media"><div class="media-body">
    <h4 class="il-item-notification-title">Neue Nachricht im Beispielforum</h4>
    <div class="il-item-description">Synthetische Benachrichtigung</div><hr class="il-item-divider"/>
    <div class="row il-item-properties"><div class="col-sm-12 il-multi-line-cap-3"><span class="il-item-property-name">Zeit</span><span class="il-item-property-value">6. Okt 2026, 14:20</span></div></div>
   </div></div></div></div></div></div></li>
  <li role="none"><span aria-label="Ihr Profilbild" class="il-avatar il-avatar-letter il-avatar-size-large il-avatar-letter-color-3" role="img"><span class="abbreviation">tn</span></span></li>
  <li role="none"><div class="il-maincontrols-slate"><div class="il-maincontrols-slate-content">
   <a class="il-link link-bulky" href="{b}/logout.php?baseClass=ilstartupgui&amp;cmd=doLogout"><span class="bulky-label">Abmelden</span></a>
  </div></div></li>
 </ul>"""

    @staticmethod
    def permission_alert() -> str:
        return ('<div class="ilAdminRow"><div class="alert alert-danger" role="alert">'
                '<div class="ilAccHeadingHidden">Fehlermeldung</div>'
                'Sie haben keine Berechtigung, auf das Objekt zuzugreifen.</div></div>')

    def tabs_html(self, ref: int) -> str:
        return (f'<ul class="nav ilCollapsable hidden-print" id="ilTab">'
                f'<li class="active" id="tab_view_content"><a href="ilias.php?baseClass=ilrepositorygui&amp;ref_id={ref}">'
                'Inhalt <span class="ilAccHidden">(Ausgewählt)</span></a></li>'
                f'<li class="" id="tab_info_short"><a href="ilias.php?baseClass=ilrepositorygui&amp;cmd=showSummary&amp;ref_id={ref}">Info</a></li>'
                '<li id="ilLastTab"><a aria-label="Mehr zeigen" class="btn dropdown-toggle ilNoDisplay" data-toggle="dropdown" href="#">'
                '... <span class="caret"></span></a><ul class="dropdown-menu" id="ilTabDropDown"></ul></li></ul>')

    def page(self, title: str, content: str, *, alert: str = "", tabs: int | None = None, logged_in: bool = True) -> str:
        t = _e(title)
        b = self.ilias_base
        return f"""<!DOCTYPE html>
<html lang="de" dir="ltr">
<head><meta charset="UTF-8"><title>{t}</title></head>
<body><div class="il-layout-page">
 <header><div class="header-inner">
  <div class="il-logo"><a href="{b}/go/root/1"><img alt="Logo" src="./templates/default/images/logo/HeaderIcon.svg"/></a></div>
  <div class="il-pagetitle">Testhochschule ILIAS</div>
  {self.metabar(logged_in)}
 </div></header>
 <main class="il-layout-page-content"><div class="container-fluid" id="mainspacekeeper"><div class="row">
  <div class="ilContentFixed" id="fixed_content"><div id="mainscrolldiv">
   <nav class="il-header-locator"><ul class="breadcrumb"><li><a href="{b}/go/root/1">Magazin</a></li><li><a href="{b}/go/cat/900190">Beispielfakultät</a></li></ul></nav>
   <div class="media il_HeaderInner"><div class="media-body"><h1 class="il-page-content-header media-heading ilHeader">{t}</h1></div></div>
   {self.tabs_html(tabs) if tabs else ""}
   <div class="ilTabsContentOuter"><div class="clearfix"></div>
    <div class="il_after_tabs_spacing"><a id="after_sub_tabs" name="after_sub_tabs"></a></div>
    {alert}
    <div id="ilContentContainer"><div class="row"><div class="col-sm-12" id="il_center_col">
{content}
    </div></div></div>
   </div>
  </div></div>
 </div></div></main>
 <footer><div class="il-footer-content">ILIAS v9.24 (Testinstanz)</div></footer>
</div></body></html>"""

    # -- Mitgliedschaften (ILIAS-9-UI: Panel mit il-item-group / il-std-item)
    def _std_item(self, m: dict) -> str:
        kind, ref = m["type"], m["ref_id"]
        href = f"{self.ilias_base}/go/{kind}/{ref}"
        title = _e(m["title"])
        props = list(m["props"])
        if m.get("offline"):
            props.append(("Status", "Offline"))
        props_html = ""
        if props:
            cells = "".join(
                f'<div class="col-md-6 il-multi-line-cap-3"><span class="il-item-property-name">{_e(k)}</span>'
                f'<span class="il-item-property-value">{_e(v)}</span></div>' for k, v in props)
            props_html = f'<hr class="il-item-divider"/><div class="row">{cells}</div>'
        desc = f'<div class="il-item-description">{_e(m["desc"])}</div>' if m.get("desc") else ""
        leave = "Kursmitgliedschaft beenden" if kind == "crs" else "Gruppenmitgliedschaft beenden"
        dd = self._uid()
        return f"""<li class="il-std-item-container"><div class="il-item il-std-item"><div class="media">
 <div class="media-left"><img alt="{ICON_ALT[kind]}" class="icon custom medium" src="./templates/default/images/standard/icon_{kind}.svg"/></div>
 <div class="media-body">
  <h4 class="il-item-title"><a href="{href}">{title}</a></h4>
  <div class="il-item-actions l-bar__space-keeper"><div class="l-bar__element"><div class="dropdown">
   <button aria-controls="{dd}_menu" aria-expanded="false" aria-haspopup="true" aria-label="Aktionen für {title}" class="btn btn-default dropdown-toggle" data-toggle="dropdown" id="{dd}" type="button"><span class="caret"></span></button>
   <ul class="dropdown-menu" id="{dd}_menu">
    <li><button class="btn btn-link" data-action="ilias.php?baseClass=ilrepositorygui&amp;cmd=leave&amp;ref_id={ref}" id="{self._uid()}">{leave}</button></li>
    <li><button class="btn btn-link" data-action="ilias.php?baseClass=ilrepositorygui&amp;cmd=infoScreen&amp;ref_id={ref}" id="{self._uid()}">Info</button></li>
    <li><button class="btn btn-link" data-action="ilias.php?baseClass=ilmembershipoverviewgui&amp;cmdClass=ilMembershipBlockGUI&amp;cmd=removeFromDesk&amp;type={kind}&amp;item_ref_id={ref}" id="{self._uid()}">Von Favoriten entfernen</button></li>
   </ul></div></div></div>
  {desc}{props_html}
 </div></div></div></li>"""

    def _panel(self, title: str, body: str, *, sortation: bool) -> str:
        sort = ""
        if sortation:
            sid = self._uid()
            buttons = "".join(
                f'<li><button class="btn btn-link" data-action="ilias.php?baseClass=ilmembershipoverviewgui&amp;cmdClass=ilMembershipBlockGUI'
                f'&amp;cmd=changePDItemSorting&amp;view=2&amp;sorting={key}" id="{self._uid()}">{label}</button></li>'
                for key, label in (("type", "Nach Typ sortieren"), ("alphabet", "Nach Alphabet sortieren"),
                                   ("start_date", "Nach Veranstaltungszeitraum sortieren")))
            sort = (f'<div class="panel-viewcontrols l-bar__space-keeper"><div class="il-viewcontrol-sortation l-bar__element" id="{self._uid()}">'
                    f'<div class="dropdown"><button aria-controls="{sid}_menu" aria-expanded="false" aria-haspopup="true" aria-label="Nach Ort sortieren" '
                    f'class="btn btn-default dropdown-toggle" data-toggle="dropdown" id="{sid}" type="button"><span class="caret"></span></button>'
                    f'<ul class="dropdown-menu" id="{sid}_menu">{buttons}</ul></div></div></div>')
        return (f'<div class="panel panel-secondary panel-flex"><div class="panel-heading ilHeader">'
                f'<div class="panel-title"><h2>{_e(title)}</h2></div>{sort}</div>'
                f'<div class="panel-body">{body}</div></div>')

    def membership_html(self) -> str:
        if self.membership_mode == "empty":
            # Leer-Hinweis: Markup an der HHN nicht live gesehen (Annahme: UI-Message-Box)
            return self._panel("Meine Kurse und Gruppen",
                               '<div class="alert alert-info" role="status"><div class="ilAccHeadingHidden">Information</div>'
                               'Sie sind noch keinem Kurs und keiner Gruppe beigetreten.</div>', sortation=False)
        groups: dict[str, list[str]] = {}
        for m in MEMBERSHIPS:
            groups.setdefault(m["location"], []).append(self._std_item(m))
        body = "".join(
            f'<div class="il-item-group"><h3>{_e(loc)}</h3><div class="il-item-group-items"><ul>{"".join(items)}</ul></div></div>'
            for loc, items in groups.items())
        return self._panel("Meine Kurse und Gruppen", body, sortation=True)

    def dashboard_html(self) -> str:
        favs = [m for m in MEMBERSHIPS if m["ref_id"] in FAVORITES]
        body = ('<div class="il-item-group"><h3>Favoriten</h3><div class="il-item-group-items"><ul>'
                + "".join(self._std_item(m) for m in favs) + "</ul></div></div>")
        return f'<div id="block_pditems_0">{self._panel("Favoriten", body, sortation=False)}</div>'

    # -- Container (Legacy-Liste: ilContainerBlock / ilContainerListItemOuter)
    def item_href(self, it: dict) -> tuple[str, str]:
        """(href, target) wie an der HHN pro Typ."""
        t, ref, b = it["type"], it["ref_id"], self.ilias_base
        if t == "file":
            return (f"{b}/ilias.php?baseClass=ilrepositorygui&amp;cmdClass=ilObjFileGUI&amp;cmd=sendfile&amp;ref_id={ref}",
                    "_blank" if it.get("inline") else "")
        if t == "webr":
            return f"ilias.php?baseClass=ilLinkResourceHandlerGUI&amp;ref_id={ref}&amp;cmd=calldirectlink", "_blank"
        if t == "wiki":
            return f"ilias.php?baseClass=ilWikiHandlerGUI&amp;ref_id={ref}&amp;cmd=view", "_top"
        if t == "crsr":
            return f"ilias.php?baseClass=ilrepositorygui&amp;ref_id={it['target']}", "_top"
        if t == "tst":
            return f"ilias.php?baseClass=ilrepositorygui&amp;cmdClass=ilobjtestgui&amp;ref_id={ref}", "_top"
        return f"{b}/go/{t}/{ref}", "_top"

    def _icon(self, it: dict) -> str:
        if it.get("inline"):
            # eigenes Dateisymbol über die File-Delivery (HHN: alt/title "Inline Datei", kein icon_file.svg)
            return (f'<img alt="Inline Datei" class="ilListItemIcon" '
                    f'src="{self.ilias_base}/src/FileDelivery/deliver.php/beispiel-symbol-{it["ref_id"]}" title="Inline Datei"/>')
        alt = ICON_ALT.get(it["type"], "Objekt")
        return f'<img alt="{alt}" class="ilListItemIcon" src="./templates/default/images/standard/icon_{it["type"]}.svg" title="{alt}"/>'

    def _actions(self, it: dict, parent: int, href: str) -> str:
        ref, t = it["ref_id"], it["type"]
        title = _e(it["title"])
        if t == "file":
            first = f'<li><a href="{href}" role="menuitem" target="_blank"><span>Download</span></a></li>'
            info = (f'<li><a href="{self.ilias_base}/ilias.php?baseClass=ilrepositorygui&amp;cmdClass=ilInfoScreenGUI&amp;cmd=showSummary&amp;ref_id={ref}" '
                    f'role="menuitem"><span>Information</span></a></li>')
        else:
            first = (f'<li><a href="ilias.php?baseClass=ilrepositorygui&amp;cmd=download&amp;ref_id={ref}" role="menuitem"><span>Download</span></a></li>'
                     if t == "fold" else "")
            info = f'<li><a href="ilias.php?baseClass=ilrepositorygui&amp;cmd=infoScreen&amp;ref_id={ref}" role="menuitem"><span>Info</span></a></li>'
        fav = (f'<li><a href="ilias.php?baseClass=ilrepositorygui&amp;cmdClass=ilObjCourseGUI&amp;cmd=addToDesk&amp;ref_id={parent}'
               f'&amp;type={t}&amp;item_ref_id={ref}" role="menuitem"><span>Zu Favoriten hinzufügen</span></a></li>')
        notes = (f"<li onclick=\"return ilNotes.listNotes(event, '1;{ref};{t};0;;;0', 'il.Object.redrawListItem({ref})');;\">"
                 f'<a href="#" role="menuitem"><span>Notizen</span></a></li>'
                 f"<li onclick=\"return ilTagging.listTags(event, '1;{ref};{t};0;;;0', 'il.Object.redrawListItem({ref})');;\">"
                 f'<a href="#" role="menuitem"><span>Tags setzen</span></a></li>')
        return f"""<div class="ilFloatRight"><div class="btn-group">
       <button aria-label="Aktionen für {title}" class="btn btn-default dropdown-toggle" data-container="body" data-toggle="dropdown" id="ilAdvSelListAnchorText_act_{ref}_pref_{parent}" type="button"><span class="caret"></span></button>
       <ul class="dropdown-menu pull-right" id="ilAdvSelListTable_act_{ref}_pref_{parent}" role="menu">{first}{info}{fav}{notes}</ul>
      </div></div>"""

    def _list_item(self, it: dict, parent: int, row_prefix: str) -> str:
        ref = it["ref_id"]
        href, target = self.item_href(it)
        target_attr = f' target="{target}"' if target else ""
        glyph = ""
        if it.get("inline"):
            glyph = (f'<span id="{self._uid()}"></span><a aria-label="Offenes Auge - Anklicken, um den Inhalt der Eingabe zu sehen" '
                     f'class="glyph" href="#" id="{self._uid()}" tabindex="0"><span aria-hidden="true" class="glyphicon glyphicon-eye-open"></span></a>')
        props = "".join(f'<span class="il_ItemProperty">{_e(p)}</span>' for p in it.get("props", []))
        props_html = f'<div class="ilListItemSection il_ItemProperties">{props}</div>' if props else ""
        alert = ('<div class="ilListItemSection il_ItemAlertProperties"><span class="il_ItemAlertProperty">Offline</span></div>'
                 if it.get("offline") else "")
        expand = ""
        if it["type"] == "sess":
            # zugeklappte Sitzung: Aufklapp-Link (nicht folgen, Spec §6.2)
            expand = (f'<div class="ilListItemSection"><a href="ilias.php?baseClass=ilrepositorygui&amp;ref_id={parent}&amp;expand={ref}">'
                      f'<span class="glyphicon glyphicon-triangle-right"></span></a></div>')
        return f"""<div class="ilCLI ilObjListRow" id="item_row_{row_prefix}-{ref}">
 <div class="ilContainerListItemOuter" data-list-item-id="lg_div_{ref}_pref_{parent}" id="lg_div_{ref}_pref_{parent}">
  <div class="ilContainerListItemIcon">{self._icon(it)}</div>
  <div class="ilContainerListItemContent"><div class="il_ContainerListItem">
   <div class="il_ContainerItemTitle form-inline"><h3 class="il_ContainerItemTitle">
    <a class="il_ContainerItemTitle" href="{href}"{target_attr}>{_e(it["title"])}</a>{glyph}
   </h3></div>
   <div style="float:right"></div>
   {self._actions(it, parent, href)}
   <div class="ilListItemSection il_Description"></div>
   {props_html}{alert}{expand}
   <div style="clear:both;"></div>
  </div><div style="clear:both;"></div></div>
 </div>
</div>"""

    def _blocks(self, ref: int) -> list[tuple[str, int | None, list[dict]]]:
        if ref >= CHAIN_START and ref not in CONTAINERS:
            nxt = ref + 1
            return [("Inhalt", None, [{"type": "fold", "ref_id": nxt, "title": f"Kanal-Ordner {nxt - CHAIN_START}"}])]
        blocks = [(t, g, list(items)) for t, g, items in CONTAINERS[ref]]
        extra = list(self.extra_items.get(ref, []))
        if ref == 900101 and self.endless_chain:
            extra.append({"type": "fold", "ref_id": CHAIN_START, "title": "Kanal-Ordner 0"})
        if extra:
            if not blocks:
                blocks = [("Inhalt", None, [])]
            t, g, items = blocks[-1]
            blocks[-1] = (t, g, items + extra)
        return blocks

    def container_html(self, ref: int) -> str:
        blocks = self._blocks(ref)
        if not blocks:
            # leerer Container: Markup an der HHN nicht live gesehen (Annahme)
            return '<div class="ilContainerBlock form-inline" id="bl_cntr_1"><div class="ilNoItems">Dieser Kurs enthält keine Objekte.</div></div>'
        out = []
        for i, (block_title, itgr, items) in enumerate(blocks, start=1):
            data = ""
            if itgr is not None:
                data = (f' data-behaviour="0" data-store-url="./ilias.php?baseClass=ilcontainerblockpropertiesstoragegui'
                        f'&amp;cmd=store&amp;cont_block_id=itgr_{itgr}"')
            prefix = str(itgr) if itgr is not None else "_other"
            rows = "".join(self._list_item(it, ref, prefix) for it in items)
            out.append(f"""<div class="ilContainerBlock form-inline"{data} id="bl_cntr_{i}">
 <div class="ilContainerBlockHeader"><h2 class="ilHeader ilContainerBlockHeader">{_e(block_title)}</h2><div class="pull-right"></div></div>
 <div class="ilContainerItemsContainer">{rows}</div>
</div>""")
        return "\n".join(out)

    def root_html(self) -> str:
        rows = "".join(self._list_item({"type": "cat", "ref_id": ref, "title": title}, 1, "_other")
                       for ref, title in ROOT_CATEGORIES)
        return f"""<div class="ilContainerBlock form-inline" id="bl_cntr_1">
 <div class="ilContainerBlockHeader"><h2 class="ilHeader ilContainerBlockHeader">Kategorien</h2><div class="pull-right"></div></div>
 <div class="ilContainerItemsContainer">{rows}</div>
</div>"""
