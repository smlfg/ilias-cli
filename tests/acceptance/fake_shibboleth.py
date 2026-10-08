"""Lokaler Fake für ILIAS mit SAML-Login über einen Shibboleth-IdP (nur stdlib, nur localhost).

Nachgebildet nach den echten, anonym erfassten Seiten der Uni Mannheim
(tests/fixtures/uni-mannheim/, siehe NOTES.md dort): Die IdP-Login-Seite und die
ILIAS-Login-Seite sind die Originale, nur action/csrf_token werden eingesetzt.
Consent-, Client-Storage- und SAML-POST-Seite folgen den Shibboleth-Standard-Templates.

ILIAS läuft auf http://127.0.0.1:<port>, der IdP auf http://localhost:<port>
(wie ilias.uni-mannheim.de vs. idp.uni-mannheim.de: getrennte Cookies).

  GET  {ilias}/saml.php                         -> anonyme PHPSESSID, 302 {idp}/idp/profile/SAML2/Redirect/SSO?SAMLRequest=…&RelayState=…
  GET  {idp}/idp/profile/SAML2/Redirect/SSO?SAMLRequest=… -> JSESSIONID, 302 …/SSO?execution=e1s1
  GET  {idp}/idp/profile/SAML2/Redirect/SSO?execution=e1s1 -> 200 form#login-form (csrf_token, j_username, j_password, …)
  POST {idp}/idp/profile/SAML2/Redirect/SSO?execution=e1sN -> 200 Login-Formular mit Fehler | [Consent] | [Client-Storage] | SAML-POST-Seite
  POST {ilias}/Services/Saml/lib/saml2-acs.php/default-sp  (SAMLResponse, RelayState) -> SimpleSAML-Cookies, 303 RelayState
  GET  {ilias}/saml.php?target=                 -> neue PHPSESSID (eingeloggt), 302 Dashboard
  GET  {ilias}/ilias.php?baseClass=ilDashboardGUI -> 200 Dashboard | 302 login.php?…cmd=force_login
"""

from __future__ import annotations

import base64
import html
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .fake_servers import RecordedRequest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "uni-mannheim"
SSO_PATH = "/idp/profile/SAML2/Redirect/SSO"
ACS_PATH = "/Services/Saml/lib/saml2-acs.php/default-sp"
REAL_ACTION = "/idp/profile/SAML2/Redirect/SSO?execution=e1s1"
CONSENT_DEFAULT = "_shib_idp_rememberConsent"
WRONG_PASSWORD_MESSAGE = "Das eingegebene Passwort ist falsch."


@dataclass
class IdpFlow:
    jsessionid: str
    relay_state: str
    request_id: str
    csrf: str = ""
    step: int = 1
    stage: str = "login"  # login -> consent -> storage -> done

    @property
    def execution(self) -> str:
        return f"e1s{self.step}"


@dataclass
class FakeShibWorld:
    username: str
    password: str
    ilias_client_id: str = "ILIAS"
    # Schalter für Szenarien
    consent: bool = False
    client_storage: bool = False
    idp_entry_mode: str = "normal"  # normal | garbage
    idp_post_mode: str = "normal"  # normal | garbage | error502
    acs_mode: str = "normal"  # normal | no_session (ILIAS akzeptiert die Assertion nicht)
    dashboard_mode: str = "normal"  # normal | no_marker | error503
    requests: list[RecordedRequest] = field(default_factory=list)
    valid_sessions: set[str] = field(default_factory=set)
    issued_session_ids: set[str] = field(default_factory=set)
    issued_secrets: set[str] = field(default_factory=set)  # csrf, SAMLResponse, IdP-Cookies
    flows: dict[str, IdpFlow] = field(default_factory=dict)
    pending_assertions: dict[str, str] = field(default_factory=dict)  # SAMLResponse -> RelayState
    sp_tokens: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    ilias_port: int = 0
    idp_port: int = 0
    _servers: list[ThreadingHTTPServer] = field(default_factory=list)

    @property
    def ilias_base(self) -> str:
        return f"http://127.0.0.1:{self.ilias_port}"

    @property
    def idp_base(self) -> str:
        return f"http://localhost:{self.idp_port}"

    def start(self) -> "FakeShibWorld":
        ilias = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self, "ilias"))
        idp = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self, "idp"))
        self.ilias_port = ilias.server_address[1]
        self.idp_port = idp.server_address[1]
        for srv in (ilias, idp):
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._servers.append(srv)
        return self

    def stop(self) -> None:
        for srv in self._servers:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass

    def expire_all_sessions(self) -> None:
        with self.lock:
            self.valid_sessions.clear()

    def requests_to(self, server: str) -> list[RecordedRequest]:
        return [r for r in self.requests if r.server == server]

    def secret(self, value: str) -> str:
        self.issued_secrets.add(value)
        return value


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _esapi_attr(value: str) -> str:
    """Wie Shibboleths encodeForHTMLAttribute: alles außer [A-Za-z0-9,.-_] als &#x..;"""
    return "".join(c if c.isalnum() or c in ",.-_" else f"&#x{ord(c):x};" for c in value)


def idp_login_page(flow: IdpFlow, error: str | None = None) -> str:
    page = (FIXTURES / "idp_login.html").read_text(encoding="utf-8")
    page = page.replace(REAL_ACTION, f"{SSO_PATH}?execution={flow.execution}")
    page = page.replace('name="csrf_token" value="REDACTED"', f'name="csrf_token" value="{flow.csrf}"')
    if error:
        marker = '<div class="form-group login-username-section"'
        page = page.replace(
            marker,
            f'<section><p class="form-element form-error">{html.escape(error)}</p></section>\n{marker}',
            1,
        )
    return page


def idp_consent_page(flow: IdpFlow) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8" /><title>IdP Universität Mannheim Informationsfreigabe</title></head>
<body><div class="login"><div class="login-container"><div class="panel panel-lg panel-login"><div class="panel-body">
<h1>Informationsfreigabe</h1>
<form action="{SSO_PATH}?execution={flow.execution}" method="post">
  <input type="hidden" name="csrf_token" value="{flow.csrf}" />
  <p>Sie sind dabei, auf diesen Dienst zuzugreifen: <strong>ILIAS</strong></p>
  <table id="attributeRelease">
    <tr><td>eduPersonPrincipalName</td><td>uniid@uni-mannheim.de</td></tr>
    <tr><td>mail</td><td>student@mail.uni-mannheim.de</td></tr>
  </table>
  <input type="hidden" name="_shib_idp_consentIds" value="eduPersonPrincipalName" />
  <input type="hidden" name="_shib_idp_consentIds" value="mail" />
  <div id="consentOptions">
    <input id="_shib_idp_doNotRememberConsent" type="radio" name="_shib_idp_consentOptions" value="_shib_idp_doNotRememberConsent">
    <label for="_shib_idp_doNotRememberConsent">Bei der nächsten Anmeldung erneut fragen</label>
    <input id="_shib_idp_rememberConsent" type="radio" name="_shib_idp_consentOptions" value="{CONSENT_DEFAULT}" checked>
    <label for="_shib_idp_rememberConsent">Erneut fragen, wenn sich die Informationen ändern</label>
    <input id="_shib_idp_globalConsent" type="radio" name="_shib_idp_consentOptions" value="_shib_idp_globalConsent">
    <label for="_shib_idp_globalConsent">Nicht mehr fragen</label>
  </div>
  <input type="submit" name="_eventId_AttributeReleaseRejected" value="Ablehnen" />
  <input type="submit" name="_eventId_proceed" value="Akzeptieren" />
</form>
</div></div></div></div></body></html>"""


def idp_storage_page(flow: IdpFlow) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8" /><title>Loading Session Information</title>
<script>function doStore(){{ document.form1.submit(); }}</script></head>
<body onload="doStore()">
<noscript><p><strong>Note:</strong> Since your browser does not support JavaScript, you must press the Continue button once to proceed.</p></noscript>
<form name="form1" action="{SSO_PATH}?execution={flow.execution}" method="post">
  <input type="hidden" name="csrf_token" value="{flow.csrf}" />
  <input name="shib_idp_ls_exception.shib_idp_session_ss" type="hidden" />
  <input name="shib_idp_ls_success.shib_idp_session_ss" type="hidden" value="false" />
  <input name="_eventId_proceed" type="hidden" />
  <noscript><input type="submit" value="Continue" /></noscript>
</form></body></html>"""


def saml_post_page(action: str, relay_state: str, saml_response: str) -> str:
    return f"""<!DOCTYPE html>
<html>
    <head><meta charset="utf-8" /></head>
    <body onload="document.forms[0].submit()">
        <noscript><p><strong>Note:</strong> Since your browser does not support JavaScript,
                you must press the Continue button once to proceed.</p></noscript>
        <form action="{_esapi_attr(action)}" method="post">
            <div>
                <input type="hidden" name="RelayState" value="{_esapi_attr(relay_state)}"/>
                <input type="hidden" name="SAMLResponse" value="{_esapi_attr(saml_response)}"/>
            </div>
            <noscript><div><input type="submit" value="Continue"/></div></noscript>
        </form>
    </body>
</html>"""


IDP_GARBAGE_HTML = """<!DOCTYPE html><html><head><title>Wartungsarbeiten</title></head>
<body><div class="login"><h1>IdP Universität Mannheim</h1>
<p>Der Anmeldedienst ist wegen Wartungsarbeiten vorübergehend nicht verfügbar.</p></div></body></html>"""


def ilias_dashboard(world: FakeShibWorld, with_marker: bool = True) -> str:
    user_menu = (
        """<ul class="il-maincontrols-metabar" role="menubar">
   <li role="none"><button class="btn btn-bulky" id="il_ui_fw_user" role="menuitem" aria-haspopup="true"><span class="bulky-label">Benutzer</span></button>
     <ul class="il-maincontrols-slate"><li><a href="ilias.php?baseClass=ilDashboardGUI&amp;cmd=jumpToProfile">Profil und Privatsphäre</a></li>
     <li><a href="logout.php?lang=de">Abmelden</a></li></ul></li></ul>"""
        if with_marker else ""
    )
    return f"""<!DOCTYPE html>
<html lang="de" dir="ltr"><head><meta charset="UTF-8"><title>Dashboard: ILIAS</title></head>
<body class="std"><div class="il-layout-page">
 <header class="il-header"><div class="header-inner"><div class="il-pagetitle">Dashboard</div>{user_menu}</div></header>
 <main class="il-layout-page-content"><div id="mainspacekeeper"><h1 class="ilHeader">Dashboard</h1>
  <div class="il-item-group"><h3>Kurse</h3>
   <div class="il-item"><a href="goto.php?target=crs_123456&amp;client_id={world.ilias_client_id}">Programmierung I</a></div></div>
 </div></main></div></body></html>"""


def ilias_login_page() -> str:
    return (FIXTURES / "ilias_login.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def _make_handler(world: FakeShibWorld, server_name: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _record(self, body: bytes) -> RecordedRequest:
            parsed = urllib.parse.urlsplit(self.path)
            cookies: dict[str, str] = {}
            for raw in self.headers.get_all("Cookie") or []:
                c = SimpleCookie()
                try:
                    c.load(raw)
                except Exception:
                    continue
                cookies.update({k: v.value for k, v in c.items()})
            ctype = self.headers.get("Content-Type", "")
            form = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True) if "form-urlencoded" in ctype else {}
            rec = RecordedRequest(
                server=server_name,
                method=self.command,
                path=parsed.path,
                query=urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
                headers={k: v for k, v in self.headers.items()},
                form=form,
                cookies=cookies,
            )
            with world.lock:
                world.requests.append(rec)
            return rec

        def _send(self, status: int, body: str = "", headers: list[tuple[str, str]] | None = None):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=UTF-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in headers or []:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _redirect(self, location: str, headers: list[tuple[str, str]] | None = None, status: int = 302):
            self._send(status, "", [("Location", location)] + (headers or []))

        def do_GET(self):
            rec = self._record(b"")
            (self._ilias if server_name == "ilias" else self._idp)(rec)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            rec = self._record(body)
            (self._ilias if server_name == "ilias" else self._idp)(rec)

        def _login_redirect(self):
            return self._redirect(
                f"{world.ilias_base}/login.php?client_id={world.ilias_client_id}&cmd=force_login&lang=de"
            )

        # -- ILIAS (SP) --
        def _ilias(self, rec: RecordedRequest):
            sid = rec.cookies.get("PHPSESSID")

            if rec.path == "/saml.php":
                token = rec.cookies.get("SimpleSAMLAuthToken", "")
                with world.lock:
                    authenticated = token in world.sp_tokens
                if authenticated:
                    new_sid = "samlauth" + secrets.token_hex(16)
                    with world.lock:
                        world.valid_sessions.add(new_sid)
                        world.issued_session_ids.add(new_sid)
                    return self._redirect(
                        f"{world.ilias_base}/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems",
                        [("Set-Cookie", f"PHPSESSID={new_sid}; path=/; HttpOnly; SameSite=Lax")],
                    )
                anon = "anon" + secrets.token_hex(12)
                relay = f"{world.ilias_base}/saml.php?target="
                request = base64.b64encode(f"<samlp:AuthnRequest ID='_{secrets.token_hex(8)}'/>".encode()).decode()
                loc = f"{world.idp_base}{SSO_PATH}?" + urllib.parse.urlencode({"SAMLRequest": request, "RelayState": relay})
                return self._redirect(loc, [
                    ("Set-Cookie", f"PHPSESSID={anon}; path=/; HttpOnly; SameSite=Lax"),
                    ("Set-Cookie", f"ilClientId={world.ilias_client_id}; path=/; HttpOnly; SameSite=Lax"),
                ])

            if rec.path == ACS_PATH and rec.method == "POST":
                form = {k: v[0] for k, v in rec.form.items()}
                with world.lock:
                    relay = world.pending_assertions.pop(form.get("SAMLResponse", ""), None)
                if relay is None or relay != form.get("RelayState"):
                    return self._send(400, "<h1>SimpleSAML\\Error\\Error: ACSPARAMS</h1>")
                if world.acs_mode == "no_session":
                    return self._login_redirect()
                token = world.secret("_" + secrets.token_hex(16))
                with world.lock:
                    world.sp_tokens.add(token)
                return self._redirect(relay, [
                    ("Set-Cookie", f"SimpleSAMLSessionID={secrets.token_hex(16)}; path=/; HttpOnly"),
                    ("Set-Cookie", f"SimpleSAMLAuthToken={token}; path=/; HttpOnly"),
                ], status=303)

            if rec.path == "/ilias.php":
                with world.lock:
                    valid = sid in world.valid_sessions
                if not valid:
                    return self._login_redirect()
                if world.dashboard_mode == "error503":
                    return self._send(503, "<h1>503 Service Temporarily Unavailable</h1>")
                return self._send(200, ilias_dashboard(world, with_marker=world.dashboard_mode != "no_marker"))

            if rec.path == "/login.php":
                return self._send(200, ilias_login_page())

            if rec.path in ("/", "/index.php"):
                return self._login_redirect()

            return self._send(404, "<h1>404 Not Found</h1>")

        # -- Shibboleth IdP --
        def _idp(self, rec: RecordedRequest):
            q = {k: v[0] for k, v in rec.query.items()}
            if rec.path != SSO_PATH:
                return self._send(404, "<h1>404</h1>")

            if rec.method == "GET" and "SAMLRequest" in q:
                if world.idp_entry_mode == "garbage":
                    return self._send(200, IDP_GARBAGE_HTML)
                flow = IdpFlow(
                    jsessionid=world.secret(secrets.token_hex(16).upper()),
                    relay_state=q.get("RelayState", ""),
                    request_id=secrets.token_hex(8),
                    csrf=world.secret("_" + secrets.token_hex(20)),
                )
                with world.lock:
                    world.flows[flow.jsessionid] = flow
                return self._redirect(
                    f"{world.idp_base}{SSO_PATH}?execution={flow.execution}",
                    [("Set-Cookie", f"JSESSIONID={flow.jsessionid}; Path=/idp; HttpOnly")],
                )

            with world.lock:
                flow = world.flows.get(rec.cookies.get("JSESSIONID", ""))
            if flow is None:
                return self._send(400, "<h1>Stale Request</h1><p>Sie haben über einen veralteten Link zugegriffen.</p>")

            if rec.method == "GET":
                if q.get("execution") != flow.execution or flow.stage != "login":
                    return self._send(400, "<h1>Stale Request</h1>")
                return self._send(200, idp_login_page(flow))

            if world.idp_post_mode == "error502":
                return self._send(502, "<html><body><h1>502 Bad Gateway</h1></body></html>")
            form = {k: v[0] for k, v in rec.form.items()}
            if q.get("execution") != flow.execution or form.get("csrf_token") != flow.csrf:
                return self._send(400, "<h1>Stale Request</h1><p>CSRF-Token ungültig.</p>")
            if "_eventId_proceed" not in form:
                return self._send(400, "<h1>Unbekanntes Ereignis</h1>")
            flow.step += 1
            flow.csrf = world.secret("_" + secrets.token_hex(20))

            if flow.stage == "login":
                if form.get("j_username") != world.username or form.get("j_password") != world.password:
                    return self._send(200, idp_login_page(flow, error=WRONG_PASSWORD_MESSAGE))
                if world.idp_post_mode == "garbage":
                    return self._send(200, IDP_GARBAGE_HTML)
                idp_session = world.secret(secrets.token_urlsafe(24))
                cookie = [("Set-Cookie", f"shib_idp_session={idp_session}; Path=/idp; HttpOnly")]
                flow.stage = "consent" if world.consent else ("storage" if world.client_storage else "done")
                return self._send(200, self._next_page(flow), cookie)

            if flow.stage == "consent":
                if form.get("_shib_idp_consentOptions") != CONSENT_DEFAULT or "_eventId_AttributeReleaseRejected" in form:
                    return self._send(400, "<h1>Freigabe abgelehnt</h1>")
                flow.stage = "storage" if world.client_storage else "done"
                return self._send(200, self._next_page(flow))

            if flow.stage == "storage":
                flow.stage = "done"
                return self._send(200, self._next_page(flow))

            return self._send(400, "<h1>Stale Request</h1>")

        def _next_page(self, flow: IdpFlow) -> str:
            if flow.stage == "consent":
                return idp_consent_page(flow)
            if flow.stage == "storage":
                return idp_storage_page(flow)
            saml_response = world.secret(base64.b64encode(
                f"<samlp:Response InResponseTo='_{flow.request_id}'>{secrets.token_hex(24)}</samlp:Response>".encode()
            ).decode())
            with world.lock:
                world.pending_assertions[saml_response] = flow.relay_state
            return saml_post_page(f"{world.ilias_base}{ACS_PATH}", flow.relay_state, saml_response)

    return Handler
