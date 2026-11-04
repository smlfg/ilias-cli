"""Akzeptanztests aus den drei UX-Sitzungen in ``docs/UX.md`` (Schritt R2).

Jede Sitzung läuft gegen ``tests/harness/fake_server.py`` mit den ``ux-routes`` und
``ux-formsteps`` aus der Spec. Das Tool wird als Subprozess gestartet; die Basis-URL
kommt ausschließlich über ``ILIAS_CLI_BASE_URL`` (``ux-meta.base_url_env``), damit
der Fake-Server beweist, dass die Env-Überschreibung wirkt.

Die Tests dürfen in R2 rot sein: Der Tool-Code wird erst in Schritt R3 nachgerüstet.
Sie beschreiben trotzdem das verbindliche Verhalten aus ``INTERFACE.md``/``README.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import SUPPORT_DIR, assert_no_external_network, ilias_executable

HARNESS = Path(__file__).resolve().parents[1] / "harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from fake_server import FakeServer  # noqa: E402
from ux_session import PtySession  # noqa: E402
from ux_spec import parse  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
UX = REPO / "docs" / "UX.md"
COURSE = "Beispielkurs Programmierung"
STRIP_ENV_PREFIXES = ("ILIAS_", "PYTHON_KEYRING", "XDG_", "KEYRING_")
STRIP_ENV_KEYS = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
}


def session_spec():
    spec = parse(UX)
    assert spec.errors == [], spec.errors
    return spec


class UxHarness:
    """Isoliertes HOME/Config-Verzeichnis und Subprozess-Aufrufe für eine UX-Sitzung."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "config"
        self.cwd = tmp_path / "work"
        self.keyring_file = tmp_path / "keyring" / "keyring.json"
        self.net_log = tmp_path / "net-blocked.log"
        for directory in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def session_file(self) -> Path:
        return self.config_dir / "session-hhn.json"

    def write_session(self) -> None:
        """Simuliert eine gespeicherte ILIAS-Session für die Lesesitzungen."""
        self.session_file.write_text(
            json.dumps({"PHPSESSID": "ux-acceptance-session"}), encoding="utf-8"
        )
        self.session_file.chmod(0o600)

    def env(self, base_url: str) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(STRIP_ENV_PREFIXES) and key not in STRIP_ENV_KEYS
        }
        env.update(
            {
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "ILIAS_CLI_CONFIG_DIR": str(self.config_dir),
                "ILIAS_CLI_BASE_URL": base_url,
                "ILIAS_CLI_REQUEST_INTERVAL": "0",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "NO_COLOR": "1",
                "TERM": "dumb",
                "COLUMNS": "200",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONPATH": str(SUPPORT_DIR),
                "PYTHON_KEYRING_BACKEND": "acceptance_keyring.FileKeyring",
                "ACCEPTANCE_KEYRING_FILE": str(self.keyring_file),
                "ACCEPTANCE_SANDBOX": "1",
                "ACCEPTANCE_NET_LOG": str(self.net_log),
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
            }
        )
        return env

    def run(
        self, base_url: str, *args: str, input: str = "", timeout: float = 60
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [ilias_executable(), *args],
            input=input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.env(base_url),
            cwd=self.cwd,
            timeout=timeout,
            start_new_session=True,  # kein TTY: Prompts lesen von stdin
        )


@pytest.fixture
def ux(tmp_path):
    harness = UxHarness(tmp_path)
    yield harness
    assert_no_external_network(harness)


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + "\n" + result.stderr


# ---------------------------------------------------------------- Sitzung (a): Login
def test_ux_session_installation_und_login(ux: UxHarness):
    """docs/UX.md: Installation + `ilias login` fragt Benutzer, Passwort und TOTP ab."""
    with FakeServer(session_spec(), REPO) as server:
        result = ux.run(
            server.base_url,
            "login",
            input="beispiel@example.invalid\ngeheim\n123456\n",
        )

        assert result.returncode == 0, output(result)
        assert "Login erfolgreich" in output(result)

        requests = server.requests
        assert any(
            request.method == "GET" and request.path == "/openidconnect.php"
            for request in requests
        ), "Login startet nicht bei openidconnect.php"
        assert any(
            request.method == "POST"
            and "username" in request.fields
            and "password" in request.fields
            for request in requests
        ), "Keycloak-POST ohne Benutzername/Passwort"
        assert any(
            request.method == "POST" and "otp" in request.fields
            for request in requests
        ), "TOTP-Schritt fehlt"

        assert ux.session_file.is_file(), "Session wurde nicht gespeichert"
        assert (ux.session_file.stat().st_mode & 0o777) == 0o600


# ------------------------------------------------- Sitzung (b): Kurse lesen
def test_ux_session_courses(ux: UxHarness):
    """docs/UX.md: `ilias courses` zeigt ID, Name und Semester (rein lesend)."""
    ux.write_session()
    with FakeServer(session_spec(), REPO) as server:
        result = ux.run(server.base_url, "courses")

        assert result.returncode == 0, output(result)
        text = output(result)
        assert "Beispielkurs Programmierung" in text
        assert "WiSe 2026/27" in text
        assert all(request.method == "GET" for request in server.requests), (
            "courses darf nichts auf dem Server verändern"
        )


def test_ux_session_ls_mit_kursname(ux: UxHarness):
    """docs/UX.md: `ilias ls "Kursname"` nimmt den Suchbegriff positional."""
    ux.write_session()
    with FakeServer(session_spec(), REPO) as server:
        result = ux.run(server.base_url, "ls", COURSE)

        assert result.returncode == 0, output(result)
        text = output(result)
        assert COURSE in text
        assert "Blatt 10" in text
        assert all(request.method == "GET" for request in server.requests), (
            "ls darf nichts auf dem Server verändern"
        )


# --------------------------------------------- Sitzung (c): Download mit [j/N]
def test_ux_session_download_fragt_und_schreibt_nach_j(ux: UxHarness):
    """docs/UX.md: `download` fragt `[j/N]`, erst nach `j` wird die Datei geladen."""
    ux.write_session()
    with FakeServer(session_spec(), REPO) as server:
        session = PtySession(
            [ilias_executable(), "download", COURSE],
            env=ux.env(server.base_url),
            cwd=str(ux.cwd),
        )
        try:
            assert session.expect("Download verbindlich? [j/N]", timeout=30), session.transcript
            assert server.sent_formsteps() == [], "Datei-GET schon vor der Bestätigung"
            session.send_line("j")
            code = session.wait_exit(60)
            transcript = session.transcript
        finally:
            session.close()

        assert code == 0, transcript
        assert "Heruntergeladen" in transcript
        assert [step_id for step_id, _ in server.sent_formsteps()] == ["datei_laden"]
        assert server.missing_formsteps() == []

        target = ux.cwd / COURSE / "Blatt 10.pdf"
        assert target.is_file(), f"Datei fehlt: {target}"
        assert target.read_bytes().startswith(b"%PDF")


def test_ux_session_download_bricht_ohne_tty_und_flag_ab(ux: UxHarness):
    """docs/UX.md/INTERFACE.md: ohne TTY und ohne `--confirm` kein Schreibzugriff."""
    ux.write_session()
    with FakeServer(session_spec(), REPO) as server:
        result = ux.run(server.base_url, "download", COURSE, input="j\n")

        assert result.returncode != 0, output(result)
        assert server.sent_formsteps() == [], "Datei-GET trotz fehlender Bestätigung"
        text = output(result)
        assert "--confirm" in text or "Abgebrochen" in text or "TTY" in text, text
        assert not (ux.cwd / COURSE).exists(), "Es wurde trotz Abbruch geschrieben"
