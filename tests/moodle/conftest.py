"""Harness für die Moodle-Tests: CLI als Subprozess gegen lokalen Fake-Moodle."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from .fake_moodle import PASSWORD, USERNAME, FakeMoodle

ACCEPTANCE_SUPPORT = Path(__file__).resolve().parent.parent / "acceptance" / "support"
STRIP_ENV_PREFIXES = ("ILIAS_", "PYTHON_KEYRING", "XDG_", "KEYRING_")
STRIP_ENV_KEYS = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"}

_orig_getaddrinfo = socket.getaddrinfo


def _blocked(host) -> bool:
    if host is None:
        return False
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").lower()
    return host not in {"localhost", "127.0.0.1", "::1"} and not host.startswith("127.")


def _guarded(host, *args, **kwargs):
    if _blocked(host):
        pytest.fail(f"Zugriff auf Nicht-localhost-Host {host!r} versucht")
    return _orig_getaddrinfo(host, *args, **kwargs)


@pytest.fixture(autouse=True)
def _no_external_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _guarded)


def ilias_executable() -> str:
    override = os.environ.get("ILIAS_BIN")
    if override:
        return override
    candidate = Path(sys.executable).parent / ("ilias.exe" if os.name == "nt" else "ilias")
    if candidate.exists():
        return str(candidate)
    return shutil.which("ilias") or pytest.fail("ilias nicht gefunden")


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str

    def json(self):
        return json.loads(self.stdout.strip())


class MoodleHarness:
    def __init__(self, tmp_path: Path, world: FakeMoodle, keyring_mode: str = "fake"):
        self.world = world
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "config"
        self.keyring_file = tmp_path / "keyring" / "keyring.json"
        self.net_log = tmp_path / "net-blocked.log"
        self.cwd = tmp_path / "work"
        for d in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.keyring_mode = keyring_mode
        self.runs: list[RunResult] = []
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def write_config(self, extra: str = "") -> None:
        (self.config_dir / "config.toml").write_text(
            f'base_url = "{self.world.base_url}"\nlms = "moodle"\ninstance = "hs-mannheim"\n{extra}',
            encoding="utf-8",
        )

    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(STRIP_ENV_PREFIXES) and k not in STRIP_ENV_KEYS}
        env.update({
            "HOME": str(self.home),
            "NO_PROXY": "127.0.0.1,localhost",
            "NO_COLOR": "1",
            "TERM": "dumb",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(ACCEPTANCE_SUPPORT),
            "ACCEPTANCE_KEYRING_FILE": str(self.keyring_file),
            "ACCEPTANCE_SANDBOX": "1",
            "ACCEPTANCE_NET_LOG": str(self.net_log),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ILIAS_CLI_CONFIG_DIR": str(self.config_dir),
        })
        env["PYTHON_KEYRING_BACKEND"] = (
            "acceptance_keyring.FileKeyring" if self.keyring_mode == "fake" else "keyring.backends.fail.Keyring"
        )
        return env

    def run(self, *args: str, input: str | None = None, timeout: float = 60) -> RunResult:
        proc = subprocess.run(
            [ilias_executable(), *args],
            input=input if input is not None else "",
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=self.env(), cwd=self.cwd, timeout=timeout, start_new_session=True,
        )
        res = RunResult(proc.returncode, proc.stdout, proc.stderr)
        self.runs.append(res)
        return res

    def login(self, *extra: str, username: str = USERNAME, password: str = PASSWORD) -> RunResult:
        return self.run("login", *extra, input=f"{username}\n{password}\n")

    def written_files(self) -> list[Path]:
        out = []
        for base in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            for p in base.rglob("*"):
                if p.is_file() and p.name not in {"config.toml"}:
                    out.append(p)
        return out

    def keyring_data(self) -> dict:
        if not self.keyring_file.exists():
            return {}
        return json.loads(self.keyring_file.read_text(encoding="utf-8"))

    def all_output(self) -> str:
        return "\n".join(r.stdout + "\n" + r.stderr for r in self.runs)

    def check_net_log(self) -> None:
        if self.net_log.exists() and self.net_log.read_text().strip():
            pytest.fail("Netzwerkzugriff außerhalb von localhost:\n" + self.net_log.read_text())


@pytest.fixture
def world():
    w = FakeMoodle().start()
    yield w
    w.stop()


@pytest.fixture
def h(tmp_path, world):
    harness = MoodleHarness(tmp_path, world)
    harness.write_config()
    yield harness
    harness.check_net_log()
