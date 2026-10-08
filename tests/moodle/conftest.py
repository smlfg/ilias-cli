"""Harness für die Moodle-Login-Tests (nur localhost).

Getestet wird über die öffentliche CLI (Subprozess `ilias`), Konfiguration per
``ILIAS_CLI_CONFIG_DIR/config.toml`` und HTTP gegen ``fake_moodle.py``.
Ein sitecustomize-Guard blockiert jeden Nicht-localhost-Zugriff und lässt den
Test fehlschlagen.
"""

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

USERNAME = "stud.user"
PASSWORD = "M00dle-Pa55w0rd-7Qx!"
SUPPORT_DIR = Path(__file__).parent / "support"
STRIP_ENV_PREFIXES = ("ILIAS_", "PYTHON_KEYRING", "XDG_", "KEYRING_")
STRIP_ENV_KEYS = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
}


def ilias_executable() -> str:
    override = os.environ.get("ILIAS_BIN")
    if override:
        return override
    candidate = Path(sys.executable).parent / ("ilias.exe" if os.name == "nt" else "ilias")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("ilias")
    if not found:
        pytest.fail("Kommando `ilias` nicht gefunden (Projekt mit `uv sync` installieren oder ILIAS_BIN setzen)")
    return found


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def file_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


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
        return (
            f"ilias {' '.join(self.args)} -> exit {self.exit_code}\n"
            f"--- stdout ---\n{self.stdout}\n--- stderr ---\n{self.stderr}"
        )


class Harness:
    def __init__(self, tmp_path: Path, world: FakeMoodle) -> None:
        self.world = world
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "config"
        self.keyring_file = tmp_path / "keyring" / "keyring.json"
        self.net_log = tmp_path / "net-blocked.log"
        self.cwd = tmp_path / "work"
        for directory in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            directory.mkdir(parents=True, exist_ok=True)
        self.keyring_mode = "fake"  # fake | none
        self.use_config_dir_env = True
        self.runs: list[RunResult] = []
        self.write_config()

    # -- Konfiguration ---------------------------------------------------
    def write_config(
        self,
        *,
        instance: str | None = "hs-mannheim",
        base_url: str | None = None,
        lms: str | None = None,
        client_id: str | None = None,
        path: Path | None = None,
    ) -> Path:
        path = path or (self.config_dir / "config.toml")
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if instance is not None:
            lines.append(f'instance = "{instance}"')
        lines.append(f'base_url = "{base_url or self.world.base_url}"')
        if lms is not None:
            lines.append(f'lms = "{lms}"')
        if client_id is not None:
            lines.append(f'client_id = "{client_id}"')
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
            "moodle_keyring.FileKeyring"
            if self.keyring_mode == "fake"
            else "keyring.backends.fail.Keyring"
        )
        if self.use_config_dir_env:
            env["ILIAS_CLI_CONFIG_DIR"] = str(self.config_dir)
        return env

    # -- Aufrufe ---------------------------------------------------------
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
                check=False,
            )
            result = RunResult(tuple(args), proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            result = RunResult(
                tuple(args),
                -999,
                str(exc.stdout or ""),
                f"TIMEOUT nach {timeout}s\n{exc.stderr or ''}",
            )
        self.runs.append(result)
        return result

    def login(self, *extra: str, password: str = PASSWORD, username: str = USERNAME) -> RunResult:
        return self.run("login", *extra, input=f"{username}\n{password}\n")

    # -- Inspektion ------------------------------------------------------
    def written_files(self) -> list[Path]:
        out: list[Path] = []
        for base in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            for path in base.rglob("*"):
                if path.is_file() and path.name != "config.toml":
                    out.append(path)
        return out

    def files_containing(self, needle: str) -> list[Path]:
        hits: list[Path] = []
        for path in self.written_files():
            try:
                if needle.encode() in path.read_bytes():
                    hits.append(path)
            except OSError:
                pass
        return hits

    def all_output(self) -> str:
        return "\n".join(r.stdout + "\n" + r.stderr for r in self.runs)


@pytest.fixture
def world():
    fake = FakeMoodle(username=USERNAME, password=PASSWORD).start()
    yield fake
    fake.stop()


@pytest.fixture
def h(tmp_path, world) -> Harness:
    harness = Harness(tmp_path, world)
    yield harness
    assert_no_external_network(harness)


def assert_no_external_network(harness: Harness) -> None:
    if harness.net_log.exists() and harness.net_log.read_text().strip():
        pytest.fail(
            "Netzwerkzugriff außerhalb von localhost versucht (blockiert):\n"
            + harness.net_log.read_text()
        )
