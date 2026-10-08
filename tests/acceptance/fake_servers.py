"""Lokale Fake-Server für ILIAS und Keycloak (nur stdlib, nur localhost).

ILIAS läuft auf http://127.0.0.1:<port>[/prefix], Keycloak auf http://localhost:<port>.
Zwei Hostnamen, damit Cookies von ILIAS und Keycloak getrennt sind (wie in echt:
ilias.hs-heilbronn.de vs. login.hs-heilbronn.de).

Der Ablauf bildet den echten HHN-Flow nach (Stand 07.10.2026, siehe ANFORDERUNGEN.md §4):
  GET  {ilias}/openidconnect.php            -> 302 Keycloak /realms/hhn/protocol/openid-connect/auth?client_id=hhn_common_ilias&...
  GET  {kc}/realms/hhn/protocol/openid-connect/auth -> 200 Login-Formular (#kc-form-login, action mit session_code/execution/tab_id)
  POST {kc}/realms/hhn/login-actions/authenticate?...  -> 200 TOTP-Formular (#kc-otp-login-form, Feld otp) | 200 Login-Formular mit Fehler
  POST {kc}/realms/hhn/login-actions/authenticate?...  -> 302 {ilias}/openidconnect.php?code=...&state=... | 200 TOTP-Formular mit Fehler
  GET  {ilias}/openidconnect.php?code=...   -> Set-Cookie PHPSESSID (neu, eingeloggt) -> 302 Dashboard
  GET  {ilias}/ilias.php?baseClass=ilDashboardGUI -> 200 Dashboard | 302 login.php?...cmd=force_login (abgelaufen)
"""

from __future__ import annotations

import html
import secrets
import threading
import urllib.parse
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KC_CLIENT_ID = "hhn_common_ilias"
REALM = "hhn"


@dataclass
class RecordedRequest:
    server: str  # "ilias" | "keycloak"
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    form: dict[str, list[str]]
    cookies: dict[str, str]


@dataclass
class KcAuthSession:
    auth_session_id: str
    tab_id: str
    redirect_uri: str
    state: str
    session_code: str
    execution: str
    hidden_nonce: str
    stage: str = "password"  # password -> otp -> done


@dataclass
class FakeWorld:
    username: str
    password: str
    totp: str
    ilias_client_id: str = "iliashhn"
    ilias_prefix: str = ""
    # Schalter für Fehlerszenarien
    keycloak_auth_mode: str = "normal"  # normal | garbage
    keycloak_post_mode: str = "normal"  # normal | error502
    dashboard_mode: str = "normal"  # normal | error503 | no_marker | login_inline
    # Rückkehr zu ILIAS nach Keycloak: normal | no_new_session (kein neues PHPSESSID)
    # | session_not_valid (neues PHPSESSID, das ILIAS aber nicht als eingeloggt kennt)
    callback_mode: str = "normal"
    requests: list[RecordedRequest] = field(default_factory=list)
    valid_sessions: set[str] = field(default_factory=set)
    issued_session_ids: set[str] = field(default_factory=set)
    kc_sessions: dict[str, KcAuthSession] = field(default_factory=dict)
    codes: dict[str, str] = field(default_factory=dict)  # code -> state
    ilias_states: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    ilias_port: int = 0
    kc_port: int = 0
    _servers: list[ThreadingHTTPServer] = field(default_factory=list)

    # ---- URLs ---------------------------------------------------------
    @property
    def ilias_base(self) -> str:
        return f"http://127.0.0.1:{self.ilias_port}{self.ilias_prefix}"

    @property
    def kc_base(self) -> str:
        return f"http://localhost:{self.kc_port}"

    # ---- Lifecycle ----------------------------------------------------
    def start(self) -> "FakeWorld":
        ilias = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self, "ilias"))
        kc = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self, "keycloak"))
        self.ilias_port = ilias.server_address[1]
        self.kc_port = kc.server_address[1]
        for srv in (ilias, kc):
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._servers.append(srv)
        return self

    def stop_ilias(self) -> None:
        srv = self._servers[0]
        srv.shutdown()
        srv.server_close()

    def stop(self) -> None:
        for srv in self._servers:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass

    # ---- Helfer für Tests ---------------------------------------------
    def expire_all_sessions(self) -> None:
        with self.lock:
            self.valid_sessions.clear()

    def requests_to(self, server: str) -> list[RecordedRequest]:
        return [r for r in self.requests if r.server == server]


# ---------------------------------------------------------------------------
# HTML-Templates (angelehnt an Keycloak-Theme "keycloak.v2" und ILIAS 9)
# ---------------------------------------------------------------------------

def _kc_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html class="login-pf" lang="de">
<head>
  <meta charset="utf-8">
  <meta name="robots" content="noindex, nofollow">
  <title>{title}</title>
  <link href="/resources/abc12/login/keycloak.v2/css/styles.css" rel="stylesheet" />
  <script type="module" src="/resources/abc12/login/keycloak.v2/js/passwordVisibility.js"></script>
</head>
<body id="keycloak-bg" class="">
<div class="pf-v5-c-login">
  <div class="pf-v5-c-login__container">
    <header id="kc-header" class="pf-v5-c-login__header"><div id="kc-header-wrapper" class="pf-v5-c-brand">HHN Login</div></header>
    <main class="pf-v5-c-login__main">
      <div class="pf-v5-c-login__main-header"><h1 class="pf-v5-c-title pf-m-3xl" id="kc-page-title">{title}</h1></div>
      <div class="pf-v5-c-login__main-body">
{body}
      </div>
    </main>
  </div>
</div>
</body>
</html>"""


def kc_login_form(world: FakeWorld, s: KcAuthSession, error: str | None = None) -> str:
    action = (
        f"{world.kc_base}/realms/{REALM}/login-actions/authenticate?"
        + urllib.parse.urlencode(
            {"session_code": s.session_code, "execution": s.execution, "client_id": KC_CLIENT_ID, "tab_id": s.tab_id}
        )
    )
    err_html = ""
    if error:
        err_html = f'''<div class="pf-v5-c-alert pf-m-danger pf-m-inline" aria-live="polite">
          <span class="kc-feedback-text">{html.escape(error)}</span></div>'''
    field_err = (
        f'<span id="input-error" class="pf-v5-c-helper-text__item pf-m-error kc-feedback-text" aria-live="polite">{html.escape(error)}</span>'
        if error else ""
    )
    body = f"""{err_html}
        <form id="kc-form-login" class="pf-v5-c-form" onsubmit="login.disabled = true; return true;" action="{html.escape(action)}" method="post" novalidate="novalidate">
          <div class="pf-v5-c-form__group">
            <label for="username" class="pf-v5-c-form__label"><span class="pf-v5-c-form__label-text">Benutzername oder E-Mail</span></label>
            <span class="pf-v5-c-form-control"><input id="username" name="username" value="" type="text" autocomplete="username" autofocus aria-invalid="{'true' if error else ''}"/></span>
            {field_err}
          </div>
          <div class="pf-v5-c-form__group">
            <label for="password" class="pf-v5-c-form__label"><span class="pf-v5-c-form__label-text">Passwort</span></label>
            <div class="pf-v5-c-input-group"><span class="pf-v5-c-form-control"><input id="password" name="password" value="" type="password" autocomplete="current-password" aria-invalid=""/></span>
            <button class="pf-v5-c-button pf-m-control" type="button" aria-label="Passwort anzeigen" data-password-toggle>👁</button></div>
          </div>
          <div class="pf-v5-c-form__group"><div class="pf-v5-c-check"><label class="pf-v5-c-check__label" for="rememberMe">
            <input class="pf-v5-c-check__input" type="checkbox" id="rememberMe" name="rememberMe"> Angemeldet bleiben</label></div></div>
          <input type="hidden" id="id-hidden-input" name="credentialId" value=""/>
          <input type="hidden" name="kc_acceptance_nonce" value="{s.hidden_nonce}"/>
          <div class="pf-v5-c-form__group pf-m-action">
            <button class="pf-v5-c-button pf-m-primary pf-m-block" name="login" id="kc-login" type="submit">Anmelden</button>
          </div>
        </form>"""
    return _kc_page("Melden Sie sich bei Ihrem Konto an", body)


def kc_otp_form(world: FakeWorld, s: KcAuthSession, error: str | None = None) -> str:
    action = (
        f"{world.kc_base}/realms/{REALM}/login-actions/authenticate?"
        + urllib.parse.urlencode(
            {"session_code": s.session_code, "execution": s.execution, "client_id": KC_CLIENT_ID, "tab_id": s.tab_id}
        )
    )
    field_err = (
        f'<span id="input-error-otp-code" class="pf-v5-c-helper-text__item pf-m-error kc-feedback-text" aria-live="polite">{html.escape(error)}</span>'
        if error else ""
    )
    body = f"""
        <form id="kc-otp-login-form" class="pf-v5-c-form" action="{html.escape(action)}" method="post" novalidate="novalidate">
          <div class="pf-v5-c-form__group">
            <label for="otp" class="pf-v5-c-form__label"><span class="pf-v5-c-form__label-text">Einmalcode</span></label>
            <span class="pf-v5-c-form-control"><input id="otp" name="otp" autocomplete="one-time-code" type="text" inputmode="numeric" autofocus aria-invalid="{'true' if error else ''}"/></span>
            {field_err}
          </div>
          <input type="hidden" name="kc_acceptance_nonce" value="{s.hidden_nonce}"/>
          <div class="pf-v5-c-form__group pf-m-action">
            <input class="pf-v5-c-button pf-m-primary pf-m-block" name="login" id="kc-login" type="submit" value="Anmelden"/>
          </div>
        </form>"""
    return _kc_page("Anmeldung mit Authenticator-App", body)


def kc_error_page(msg: str) -> str:
    return _kc_page("Es ist ein Fehler aufgetreten", f'<div id="kc-error-message"><p class="instruction">{html.escape(msg)}</p></div>')


GARBAGE_HTML = """<!DOCTYPE html><html><head><title>Wartungsarbeiten</title></head>
<body><h1>Wartungsarbeiten</h1><p>Der Anmeldedienst ist vorübergehend nicht verfügbar. Bitte versuchen Sie es später erneut.</p>
<div class="maintenance"><img src="/static/hhn-logo.svg" alt="HHN"></div></body></html>"""

NO_MARKER_HTML = """<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><title>ILIAS Hochschule Heilbronn</title></head>
<body class="std"><div class="il-layout-page"><main class="il-layout-page-content">
<div class="alert alert-info" role="status">Die Installation befindet sich im Wartungsmodus.</div>
</main></div></body></html>"""


def ilias_dashboard(world: FakeWorld) -> str:
    p = world.ilias_prefix
    return f"""<!DOCTYPE html>
<html lang="de" dir="ltr">
<head><meta charset="UTF-8"><title>Dashboard - ILIAS Hochschule Heilbronn</title>
<link rel="stylesheet" type="text/css" href="./templates/default/delos.css?vers=9-24" /></head>
<body class="std">
<div class="il-layout-page">
 <header class="il-header"><div class="header-inner">
  <div class="il-logo"><a href="{p}/goto.php?target=root_1&amp;client_id={world.ilias_client_id}"><img src="./templates/default/images/logo/HeaderIcon.svg" alt="Zum Magazin"/></a></div>
  <div class="il-pagetitle">Dashboard</div>
  <ul class="il-maincontrols-metabar" role="menubar">
   <li role="none"><button class="btn btn-bulky" data-action="" id="il_ui_fw_user" role="menuitem" aria-haspopup="true"><span class="glyph" aria-label="Benutzer"></span><span class="bulky-label">Benutzer</span></button>
     <ul class="il-maincontrols-slate"><li><a href="{p}/ilias.php?baseClass=ilDashboardGUI&amp;cmd=jumpToProfile">Profil und Privatsphäre</a></li>
     <li><a href="{p}/logout.php?lang=de">Abmelden</a></li></ul></li>
  </ul></div></header>
 <main class="il-layout-page-content"><div id="mainspacekeeper">
  <h1 class="ilHeader">Dashboard</h1>
  <div class="il-item-group"><h3>Kurse</h3>
   <div class="il-item"><a href="{p}/goto.php?target=crs_174021&amp;client_id={world.ilias_client_id}">Mathematik 1 (AKIB)</a></div>
  </div>
 </div></main>
 <footer class="il-footer">ILIAS v9.24 (2026-10-06)</footer>
</div></body></html>"""


def ilias_login_page(world: FakeWorld) -> str:
    p = world.ilias_prefix
    return f"""<!DOCTYPE html>
<html lang="de" dir="ltr">
<head><meta charset="UTF-8"><title>ILIAS Hochschule Heilbronn</title></head>
<body class="std">
<div class="il-layout-page"><main class="il-layout-page-content"><div id="mainspacekeeper">
 <div class="ilStartupFrame">
  <h1>Anmelden bei ILIAS</h1>
  <div class="ilStartupSection">
   <a class="btn btn-default" href="{p}/openidconnect.php">Mit HHN-Konto anmelden</a>
  </div>
  <details><summary>Ohne HHN-Konto anmelden</summary>
  <form id="form_" class="il-standard-form form-horizontal" enctype="multipart/form-data" method="post" name="formlogin"
        action="{p}/ilias.php?client_id={world.ilias_client_id}&amp;cmd=post&amp;cmdClass=ilstartupgui&amp;cmdNode=10i&amp;baseClass=ilStartUpGUI&amp;rtoken=">
    <input type="text" id="username" name="username" value=""/>
    <input type="password" id="password" name="password" value="" autocomplete="off"/>
    <input class="btn btn-default" type="submit" name="cmd[doStandardAuthentication]" value="Anmelden"/>
  </form></details>
 </div>
 <p class="small">ILIAS v9.24 (2026-10-06)</p>
</div></main></div></body></html>"""


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def _make_handler(world: FakeWorld, server_name: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # still
            pass

        # -- infra --
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

        def _send(self, status: int, body: str = "", headers: list[tuple[str, str]] | None = None, ctype: str = "text/html; charset=UTF-8"):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, must-revalidate, max-age=0")
            for k, v in headers or []:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _redirect(self, location: str, headers: list[tuple[str, str]] | None = None):
            self._send(302, "", [("Location", location)] + (headers or []))

        def do_GET(self):
            rec = self._record(b"")
            (self._ilias if server_name == "ilias" else self._keycloak)(rec)

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            rec = self._record(body)
            (self._ilias if server_name == "ilias" else self._keycloak)(rec)

        # -- ILIAS --
        def _ilias(self, rec: RecordedRequest):
            prefix = world.ilias_prefix
            path = rec.path
            if prefix:
                if not path.startswith(prefix + "/"):
                    return self._send(404, "<h1>404 Not Found</h1>")
                path = path[len(prefix):]
            q = {k: v[0] for k, v in rec.query.items()}
            sid = rec.cookies.get("PHPSESSID")

            if path == "/openidconnect.php":
                if "code" not in q:
                    state = secrets.token_hex(16)
                    anon = "anon" + secrets.token_hex(12)
                    with world.lock:
                        world.ilias_states.add(state)
                    redirect_uri = f"{world.ilias_base}/openidconnect.php"
                    loc = f"{world.kc_base}/realms/{REALM}/protocol/openid-connect/auth?" + urllib.parse.urlencode({
                        "response_type": "code", "redirect_uri": redirect_uri, "client_id": KC_CLIENT_ID,
                        "nonce": secrets.token_hex(16), "state": state, "scope": "openid profile email",
                    })
                    return self._redirect(loc, [
                        ("Set-Cookie", f"PHPSESSID={anon}; path={prefix or '/'}; HttpOnly; SameSite=Lax"),
                        ("Set-Cookie", f"ilClientId={world.ilias_client_id}; path={prefix or '/'}; HttpOnly; SameSite=Lax"),
                    ])
                code, state = q.get("code", ""), q.get("state", "")
                with world.lock:
                    ok = world.codes.pop(code, None) == state and state in world.ilias_states
                if not ok:
                    return self._redirect(f"{world.ilias_base}/login.php?client_id={world.ilias_client_id}&cmd=force_login&lang=de")
                if world.callback_mode == "no_new_session":
                    return self._redirect(f"{world.ilias_base}/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems")
                new_sid = "auth" + secrets.token_hex(16)
                with world.lock:
                    if world.callback_mode != "session_not_valid":
                        world.valid_sessions.add(new_sid)
                    world.issued_session_ids.add(new_sid)
                return self._redirect(
                    f"{world.ilias_base}/ilias.php?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems",
                    [("Set-Cookie", f"PHPSESSID={new_sid}; path={prefix or '/'}; HttpOnly; SameSite=Lax"),
                     ("Set-Cookie", f"ilClientId={world.ilias_client_id}; path={prefix or '/'}; HttpOnly; SameSite=Lax")],
                )

            if path == "/ilias.php":
                with world.lock:
                    valid = sid in world.valid_sessions
                if not valid:
                    target = urllib.parse.quote("", safe="")
                    return self._redirect(
                        f"{world.ilias_base}/login.php?target={target}&client_id={world.ilias_client_id}&cmd=force_login&lang=de"
                    )
                if world.dashboard_mode == "error503":
                    return self._send(503, "<h1>503 Service Temporarily Unavailable</h1><hr><center>nginx</center>")
                if world.dashboard_mode == "no_marker":
                    return self._send(200, NO_MARKER_HTML)
                if world.dashboard_mode == "login_inline":
                    return self._send(200, ilias_login_page(world))
                return self._send(200, ilias_dashboard(world))

            if path == "/login.php":
                return self._send(200, ilias_login_page(world))

            if path == "/logout.php":
                with world.lock:
                    world.valid_sessions.discard(sid)
                return self._redirect(f"{world.ilias_base}/login.php?client_id={world.ilias_client_id}&cmd=force_logout&lang=de")

            if path in ("/", "/index.php"):
                return self._redirect(f"{world.ilias_base}/login.php?client_id={world.ilias_client_id}&cmd=force_login&lang=de")

            return self._send(404, "<h1>404 Not Found</h1><hr><center>nginx</center>")

        # -- Keycloak --
        def _keycloak(self, rec: RecordedRequest):
            q = {k: v[0] for k, v in rec.query.items()}
            if rec.path == f"/realms/{REALM}/protocol/openid-connect/auth" and rec.method == "GET":
                if q.get("client_id") != KC_CLIENT_ID or "redirect_uri" not in q or "state" not in q:
                    return self._send(400, kc_error_page("Ungültiger Parameter: redirect_uri"))
                if world.keycloak_auth_mode == "garbage":
                    return self._send(200, GARBAGE_HTML)
                s = KcAuthSession(
                    auth_session_id=secrets.token_hex(16) + "." + "keycloak-0",
                    tab_id=secrets.token_urlsafe(8),
                    redirect_uri=q["redirect_uri"],
                    state=q["state"],
                    session_code=secrets.token_urlsafe(32),
                    execution="2b8e4f01-6f8a-4c9e-9a59-1a2b3c4d5e6f",
                    hidden_nonce=secrets.token_hex(8),
                )
                with world.lock:
                    world.kc_sessions[s.auth_session_id] = s
                return self._send(200, kc_login_form(world, s), [
                    ("Set-Cookie", f"AUTH_SESSION_ID={s.auth_session_id}; Version=1; Path=/realms/{REALM}/; HttpOnly; SameSite=None"),
                    ("Set-Cookie", f"KC_RESTART=eyJhbGciOiJIUzUxMiJ9.{secrets.token_urlsafe(24)}; Version=1; Path=/realms/{REALM}/; HttpOnly"),
                ])

            if rec.path == f"/realms/{REALM}/login-actions/authenticate" and rec.method == "POST":
                if world.keycloak_post_mode == "error502":
                    return self._send(502, "<html><body><h1>502 Bad Gateway</h1></body></html>")
                with world.lock:
                    s = world.kc_sessions.get(rec.cookies.get("AUTH_SESSION_ID", ""))
                if s is None:
                    return self._send(400, kc_error_page("Cookie nicht gefunden. Bitte stellen Sie sicher, dass Cookies in Ihrem Browser aktiviert sind."))
                if (q.get("session_code") != s.session_code or q.get("execution") != s.execution
                        or q.get("tab_id") != s.tab_id or q.get("client_id") != KC_CLIENT_ID):
                    return self._send(400, kc_error_page("Die Seite ist abgelaufen. Bitte versuchen Sie es erneut."))
                form = {k: v[0] for k, v in rec.form.items()}
                if form.get("kc_acceptance_nonce") != s.hidden_nonce:
                    return self._send(400, kc_error_page("Ungültige Anfrage."))
                s.session_code = secrets.token_urlsafe(32)
                if s.stage == "password":
                    if form.get("username") == world.username and form.get("password") == world.password:
                        s.stage = "otp"
                        s.execution = "8c1d2e3f-0a9b-4c8d-b7e6-f5a4b3c2d1e0"
                        return self._send(200, kc_otp_form(world, s))
                    return self._send(200, kc_login_form(world, s, error="Ungültiger Benutzername oder Passwort."))
                if s.stage == "otp":
                    if form.get("otp") == world.totp:
                        s.stage = "done"
                        code = secrets.token_hex(8) + "." + secrets.token_hex(16)
                        with world.lock:
                            world.codes[code] = s.state
                        loc = s.redirect_uri + "?" + urllib.parse.urlencode({
                            "state": s.state, "session_state": secrets.token_hex(8),
                            "iss": f"{world.kc_base}/realms/{REALM}", "code": code,
                        })
                        return self._redirect(loc, [
                            ("Set-Cookie", f"KEYCLOAK_IDENTITY=eyJhbGciOi.{secrets.token_urlsafe(24)}; Version=1; Path=/realms/{REALM}/; HttpOnly"),
                            ("Set-Cookie", f"KEYCLOAK_SESSION={secrets.token_hex(12)}; Version=1; Path=/realms/{REALM}/"),
                        ])
                    return self._send(200, kc_otp_form(world, s, error="Ungültiger Authenticator-Code."))
                return self._send(400, kc_error_page("Ungültige Anfrage."))

            return self._send(404, kc_error_page("Seite nicht gefunden"))

    return Handler
