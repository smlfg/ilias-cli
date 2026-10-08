"""Black-Box-Tests: Weiterleitungen beim Lesen (`courses`, `ls`) nie blind folgen.

Spec: docs/HHN_2FA_SPEC.md §7 (Reihenfolge pro Antwort, Redirect-Schutz) und §13.7/§13.10.
Die CLI läuft als Subprozess gegen den Fake aus tests/hhn/fake_hhn.py. Dieser Test erweitert ihn
nur lokal um umleitende Antworten und einen dritten Fake-Server („fremder Host“). Es gibt keine
echten Daten und keine echten Hosts; die Netzwerk-Sperre aus tests/acceptance gilt.

Für jeden Fall wird geprüft:
- Exit 3 `session_expired` (Login-/IdP-Fluss, fremder Host). Bei einer Schleife aus mehr als
  10 Weiterleitungen gilt Exit 4 `network_error`, und der Befehl darf nicht hängen.
- Die umleitende ILIAS-Seite wird genau einmal abgerufen; danach folgt kein weiterer
  ILIAS-Request (Ausnahme: Ketten innerhalb des ILIAS-Hosts, die mitgezählt werden).
- Keycloak und der fremde Host erhalten **null** Requests.
- Es gibt kein POST.
- Die gespeicherte Session bleibt unverändert, auch wenn die Weiterleitung `Set-Cookie: PHPSESSID=…` mitschickt.
- In stdout und stderr steht kein Cookie-Wert.
- Mit `--json` gibt es ein Fehlerobjekt mit `code`, `type` und `message`.

Die 12 Unit-Tests in tests/hhn_unit/test_fetch_redirects.py prüfen den Fetcher direkt.
Diese Tests hier prüfen das Verhalten des ganzen Befehls und sind implementierungsneutral.
Eigener Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_redirect_guard.py -q`
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import ThreadingHTTPServer

import pytest
from acceptance.fake_servers import RecordedRequest, _make_handler

from .conftest import PASSWORD, TOTP, USERNAME, HhnHarness
from .fake_hhn import HhnWorld
from .helpers import err_json

COURSE = 900101  # ausgedachte ref_id aus tests/hhn/fixtures/courses/data.py
ROTATED_SID = "rotated-on-redirect-0123456789abcdef"
MAX_REDIRECTS = 10  # Spec §7: höchstens 10 Weiterleitungen in Folge

# Weiterleitungsziele. Platzhalter: {ilias} ILIAS-Basis-URL, {kc} Fake-Keycloak (anderer Host und Port),
# {foreign} dritter Fake-Server (anderer Host und Port).
TARGETS = {
    "login_php": "{ilias}/login.php?client_id=iliashhn&lang=de",
    "cmd_force_login": "{ilias}/ilias.php?baseClass=ilStartUpGUI&cmd=force_login&lang=de",
    "openidconnect": "{ilias}/openidconnect.php",
    "keycloak_realms": "{kc}/realms/hhn/protocol/openid-connect/auth?client_id=hhn_common_ilias&response_type=code",
    "shibboleth_sso": "{ilias}/Shibboleth.sso/Login?target=x",
    "saml_php": "{ilias}/saml.php?target=x",
    "foreign_host": "{foreign}/ilias.php?baseClass=ilmembershipoverviewgui",
    "chain_to_keycloak": "{ilias}/rg/hop/1",  # -> /rg/hop/2 -> Keycloak
}
CHAIN_HOPS = 2  # ILIAS-interne Zwischenstationen bei chain_to_keycloak

# Befehl -> (CLI-Argumente, welche Seite umleitet)
COMMANDS = {
    "courses": (("courses", "--json"), "membership"),
    "ls": (("ls", str(COURSE), "--json"), "container"),
}


@dataclass
class RedirectWorld(HhnWorld):
    """HhnWorld + eine umleitende Seite + fremder Host. Alle Server binden an 127.0.0.1."""

    redirect_on: str = ""  # "" | "membership" | "container"
    redirect_to: str = ""  # Schlüssel aus TARGETS oder "loop"
    foreign_port: int = 0

    def start(self) -> RedirectWorld:  # type: ignore[override]
        super().start()
        foreign = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self, "foreign"))
        foreign.daemon_threads = True
        threading.Thread(target=foreign.serve_forever, daemon=True).start()
        self._servers.append(foreign)
        self.foreign_port = foreign.server_address[1]
        return self

    def target_url(self, key: str) -> str:
        return TARGETS[key].format(
            ilias=self.ilias_base, kc=self.kc_base, foreign=f"http://localhost:{self.foreign_port}"
        )

    def _bounce(self, handler, location: str) -> None:
        handler._redirect(location, [("Set-Cookie", f"PHPSESSID={ROTATED_SID}; path=/; HttpOnly")])

    def handle_repo(self, handler, rec: RecordedRequest) -> bool:
        path = rec.path[len(self.ilias_prefix):] if self.ilias_prefix else rec.path
        if path.startswith("/rg/hop/"):
            n = int(path.rsplit("/", 1)[1])
            nxt = f"{self.ilias_base}/rg/hop/{n + 1}" if n < CHAIN_HOPS else self.target_url("keycloak_realms")
            self._bounce(handler, nxt)
            return True
        if path.startswith("/rg/loop/"):
            other = "b" if path.endswith("/a") else "a"
            self._bounce(handler, f"{self.ilias_base}/rg/loop/{other}")
            return True
        q = {k: v[0] for k, v in rec.query.items()}
        bc = q.get("baseClass", "").lower()
        on_membership = path == "/ilias.php" and bc == "ilmembershipoverviewgui"
        on_course = (path == "/ilias.php" and bc == "ilrepositorygui" and q.get("ref_id") == str(COURSE)) or (
            path == f"/go/crs/{COURSE}"
        )
        hit = (self.redirect_on == "membership" and on_membership) or (self.redirect_on == "container" and on_course)
        if hit:
            loc = f"{self.ilias_base}/rg/loop/a" if self.redirect_to == "loop" else self.target_url(self.redirect_to)
            self._bounce(handler, loc)
            return True
        return super().handle_repo(handler, rec)


@pytest.fixture
def rworld():
    w = RedirectWorld(username=USERNAME, password=PASSWORD, totp=TOTP).start()
    yield w
    w.stop()


@pytest.fixture
def rlogged(tmp_path, rworld) -> HhnHarness:
    h = HhnHarness(tmp_path, rworld)
    r = h.login()
    assert r.exit_code == 0, str(r)
    yield h


def _secrets(h: HhnHarness) -> list[str]:
    """Alle Cookie-Werte, die nie in einer Ausgabe stehen dürfen."""
    vals = {ROTATED_SID, *h.world.issued_session_ids}
    if h.keyring_file.exists():
        for blob in json.loads(h.keyring_file.read_text(encoding="utf-8")).values():
            try:
                vals.update(str(v) for v in json.loads(blob).values() if len(str(v)) >= 8)
            except (ValueError, AttributeError):
                pass
    return sorted(v for v in vals if v)


def _arrange(h: HhnHarness, command: str, target: str) -> tuple[tuple[str, ...], int, bytes]:
    args, where = COMMANDS[command]
    h.world.redirect_on = where
    h.world.redirect_to = target
    start = len(h.world.requests)
    return args, start, h.keyring_file.read_bytes()


def _assert_common(h: HhnHarness, r, start: int, keyring_before: bytes) -> list[RecordedRequest]:
    new = h.world.requests[start:]
    assert [x for x in new if x.server == "keycloak"] == [], "Keycloak darf beim Lesen nie kontaktiert werden"
    assert [x for x in new if x.server == "foreign"] == [], "fremder Host darf nie kontaktiert werden"
    assert all(x.method == "GET" for x in new), [(x.method, x.path) for x in new]
    assert h.keyring_file.read_bytes() == keyring_before, "gespeicherte Session darf sich nicht ändern"
    out = r.stdout + r.stderr
    for secret in _secrets(h):
        assert secret not in out, "Cookie-Wert in der Ausgabe"
    assert "Traceback" not in r.stderr, r.stderr
    data = json.loads(r.stdout)
    err = data.get("error") or {}
    assert {"code", "type", "message"} <= set(err), data
    assert err["message"], data
    return [x for x in new if x.server == "ilias"]


def _bounced(world: RedirectWorld, ilias_new: list[RecordedRequest]) -> list[int]:
    """Indizes der ILIAS-Requests auf die umleitende Seite."""
    idx = []
    for i, x in enumerate(ilias_new):
        q = {k: v[0] for k, v in x.query.items()}
        bc = q.get("baseClass", "").lower()
        if world.redirect_on == "membership" and bc == "ilmembershipoverviewgui":
            idx.append(i)
        elif world.redirect_on == "container" and (
            (bc == "ilrepositorygui" and q.get("ref_id") == str(COURSE)) or x.path.endswith(f"/go/crs/{COURSE}")
        ):
            idx.append(i)
    return idx


@pytest.mark.parametrize("command", sorted(COMMANDS))
@pytest.mark.parametrize("target", sorted(TARGETS))
def test_redirect_into_login_or_foreign_host_exit3_no_follow(rlogged: HhnHarness, command: str, target: str):
    """§7: Weiterleitung in den Login-/IdP-Fluss oder auf einen fremden Host -> Exit 3, nicht folgen."""
    args, start, before = _arrange(rlogged, command, target)
    r = rlogged.run(*args)
    err_json(r, 3, "session_expired")
    ilias_new = _assert_common(rlogged, r, start, before)
    hits = _bounced(rlogged.world, ilias_new)
    assert len(hits) == 1, f"umleitende Seite {len(hits)}x abgerufen"
    after = ilias_new[hits[0] + 1:]
    allowed = CHAIN_HOPS if target == "chain_to_keycloak" else 0
    assert len(after) == allowed, f"nach der Weiterleitung noch {[(x.path, x.query) for x in after]} abgerufen"
    assert all(x.path.startswith("/rg/hop/") for x in after), [x.path for x in after]
    if command == "courses":
        assert len(ilias_new) == 1 + allowed, f"courses: {len(ilias_new)} ILIAS-Requests (soll {1 + allowed})"


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_redirect_loop_stops_exit4_no_hang(rlogged: HhnHarness, command: str):
    """§7: Mehr als 10 Weiterleitungen in Folge -> Exit 4 network_error, ohne Hängen, ohne Keycloak/fremden Host."""
    args, start, before = _arrange(rlogged, command, "loop")
    t0 = time.monotonic()
    r = rlogged.run(*args, timeout=30)
    assert r.exit_code != -999, "Befehl hängt in der Weiterleitungsschleife"
    assert time.monotonic() - t0 < 30
    err_json(r, 4, "network_error")
    ilias_new = _assert_common(rlogged, r, start, before)
    loop = [x for x in ilias_new if x.path.startswith("/rg/loop/")]
    assert 1 <= len(loop) <= MAX_REDIRECTS, f"{len(loop)} Schleifen-Requests (höchstens {MAX_REDIRECTS})"


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_read_commands_never_post(rlogged: HhnHarness, command: str):
    """§4.3/N2: courses und ls senden nur GET (auch rekursiv), nie POST, nie an Keycloak."""
    args, _ = COMMANDS[command]
    start = len(rlogged.world.requests)
    extra = ("--depth", "3") if command == "ls" else ()
    r = rlogged.run(*args, *extra)
    assert r.exit_code == 0, str(r)
    new = rlogged.world.requests[start:]
    assert new, "Befehl hat ILIAS nicht gefragt"
    assert [(x.method, x.path) for x in new if x.method != "GET"] == []
    assert [x for x in new if x.server != "ilias"] == []
