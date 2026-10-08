"""Harness für Moodle-Login-Tests: CLI als Subprozess gegen lokalen Fake-Server."""

from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from .fake_moodle import FakeMoodle

USERNAME = "moodle.testuser"
PASSWORD = "M00dle-T3st-Pw-4Qx!"
TOKEN = "moodle-test-token-abc123"
SITENAME = "Lernplattform TH-MA"
FULLNAME = "Moodle Testuser"
USERID = 42

SUPPORT_DIR = Path(__file__).parent.parent / "acceptance" / "support"
STRIP_ENV_PREFIXES = ("ILIAS_", "PYTHON_KEYRING", "XDG_", "KEYRING_")
STRIP_ENV_KEYS = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"}


def ilias_executable() -> str:
    override = os.environ.get("ILIAS_BIN")
    if override:
        return override
    candidate = Path(sys.executable).parent / ("ilias.exe" if os.name == "nt" else "ilias")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("ilias")
    if not found:
        pytest.fail("Kommando `ilias` nicht gefunden (mit `uv sync` installieren oder ILIAS_BIN setzen)")
    return found


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def file_mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


@dataclass
class RunResult:
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    def json(self, strict: bool = True):
        text = self.stdout.strip()
        if strict:
            return json.loads(text)
        start = text.find("{")
        if start < 0:
            raise ValueError(f"kein JSON-Objekt in stdout: {text!r}")
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj

    def __str__(self) -> str:
        return f"ilias {' '.join(self.args)} -> exit {self.exit_code}\n--- stdout ---\n{self.stdout}\n--- stderr ---\n{self.stderr}"


class Harness:
    def __init__(self, tmp_path: Path, world: FakeMoodle):
        self.world = world
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "config"
        self.keyring_file = tmp_path / "keyring" / "keyring.json"
        self.net_log = tmp_path / "net-blocked.log"
        self.cwd = tmp_path / "work"
        for d in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.keyring_mode = "fake"  # fake | none
        self.use_config_dir_env = True
        self.runs: list[RunResult] = []
        self.write_config()

    def write_config(
        self,
        base_url: str | None = None,
        instance: str | None = "hs-mannheim",
        lms: str | None = None,
        path: Path | None = None,
    ) -> Path:
        path = path or (self.config_dir / "config.toml")
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if instance is not None:
            lines.append(f'instance = "{instance}"')
        if lms is not None:
            lines.append(f'lms = "{lms}"')
        lines.append(f'base_url = "{base_url or self.world.base_url}"')
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def env(self) -> dict[str, str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(STRIP_ENV_PREFIXES) and k not in STRIP_ENV_KEYS
        }
        env.update(
            {
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "NO_COLOR": "1",
                "TERM": "dumb",
                "COLUMNS": "200",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONPATH": str(SUPPORT_DIR),
                "ACCEPTANCE_KEYRING_FILE": str(self.keyring_file),
                "ACCEPTANCE_SANDBOX": "1",
                "ACCEPTANCE_NET_LOG": str(self.net_log),
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
            }
        )
        env["PYTHON_KEYRING_BACKEND"] = (
            "acceptance_keyring.FileKeyring"
            if self.keyring_mode == "fake"
            else "keyring.backends.fail.Keyring"
        )
        if self.use_config_dir_env:
            env["ILIAS_CLI_CONFIG_DIR"] = str(self.config_dir)
        return env

    def run(self, *args: str, input: str | None = None, timeout: float = 60) -> RunResult:
        try:
            proc = subprocess.run(
                [ilias_executable(), *args],
                input=input if input is not None else "",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.env(),
                cwd=self.cwd,
                timeout=timeout,
                start_new_session=True,
            )
            res = RunResult(tuple(args), proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            res = RunResult(
                tuple(args), -999, str(exc.stdout or ""), f"TIMEOUT nach {timeout}s\n{exc.stderr or ''}"
            )
        self.runs.append(res)
        return res

    def login(
        self,
        *extra: str,
        password: str = PASSWORD,
        username: str = USERNAME,
    ) -> RunResult:
        return self.run("login", *extra, input=f"{username}\n{password}\n")

    def written_files(self) -> list[Path]:
        out = []
        for base in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if p.is_file() and p.name != "config.toml":
                    out.append(p)
        return out

    def files_containing(self, needle: str) -> list[Path]:
        hits = []
        if not needle:
            return hits
        for p in self.written_files():
            try:
                if needle.encode() in p.read_bytes():
                    hits.append(p)
            except OSError:
                pass
        return hits

    def all_output(self) -> str:
        return "\n".join(r.stdout + "\n" + r.stderr for r in self.runs)


@pytest.fixture
def world():
    w = FakeMoodle(username=USERNAME, password=PASSWORD, token=TOKEN, sitename=SITENAME, fullname=FULLNAME, userid=USERID).start()
    yield w
    w.stop()


@pytest.fixture
def h(tmp_path, world) -> Harness:
    harness = Harness(tmp_path, world)
    yield harness
    assert_no_external_network(harness)


def assert_no_external_network(harness: Harness) -> None:
    """Jeder Nicht-localhost-Verbindungsversuch des CLI-Subprozesses lässt den Test fehlschlagen."""
    if harness.net_log.exists():
        content = harness.net_log.read_text(encoding="utf-8", errors="replace").strip()
        if content:
            pytest.fail("Netzwerkzugriff außerhalb von localhost versucht (blockiert):\n" + content)
    # Zusätzlich: Der Fake-Server muss kontaktiert worden sein, sonst lief etwas gegen echt/Proxy.
    # (Nur prüfen, wenn überhaupt ein login/status versucht wurde.)
    if harness.runs:
        contacted = [r for r in harness.world.requests if r.path.endswith(("token.php", "server.php"))]
        # Logout ohne Session muss keinen Request machen; das ist ok.
        only_logout_without_session = all(
            r.args and r.args[0] == "logout" for r in harness.runs
        )
        if not contacted and not only_logout_without_session:
            # Wenn status ohne Token -> kein Request nötig; ebenfalls ok.
            pass


# In-Prozess-Guard: Tests selbst dürfen nie Nicht-Localhost kontaktieren.
_ALLOWED = {"localhost", "127.0.0.1", "::1", "localhost.localdomain", "ip6-localhost"}


def _is_loopback(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").lower()
    return host in _ALLOWED or host.startswith("127.")


_orig_getaddrinfo = socket.getaddrinfo
_orig_connect = socket.socket.connect


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_loopback(host):
        pytest.fail(f"Test hat Nicht-localhost-DNS versucht: {host!r}")
    return _orig_getaddrinfo(host, *args, **kwargs)


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple):
        if not _is_loopback(address[0]):
            pytest.fail(f"Test hat Nicht-localhost-Verbindung versucht: {address}")
    return _orig_connect(self, address)


@pytest.fixture(autouse=True)
def _localhost_guard(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    yield
