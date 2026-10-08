"""Harness für die modellunabhängigen Akzeptanztests (siehe INTERFACE.md).

Getestet wird ausschließlich über die öffentliche Schnittstelle: das installierte
Kommando `ilias` als Subprozess, Konfiguration über Umgebungsvariablen/config.toml,
HTTP gegen lokale Fake-Server (fake_servers.py). Keine echten Netzwerkaufrufe.
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

from .fake_servers import FakeWorld

USERNAME = "acceptance.user"
PASSWORD = "Acc3pt-Pa55w0rd-7Qx!"  # Dummy, nur für Tests
TOTP = "246813"  # Dummy-Einmalcode
SUPPORT_DIR = Path(__file__).parent / "support"
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
        pytest.fail("Kommando `ilias` nicht gefunden (Projekt mit `uv sync` installieren oder ILIAS_BIN setzen)")
    return found


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class RunResult:
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    def json(self, strict: bool = True):
        """JSON aus stdout. strict=False erlaubt Prompt-Text vor dem JSON-Objekt (nur für login)."""
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
    def __init__(self, tmp_path: Path, world: FakeWorld):
        self.world = world
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "config"
        self.keyring_file = tmp_path / "keyring" / "keyring.json"
        self.cwd = tmp_path / "work"
        for d in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.keyring_mode = "fake"  # fake | none
        self.use_config_dir_env = True
        self.runs: list[RunResult] = []
        self.write_config()

    # -- Konfiguration --
    def write_config(self, base_url: str | None = None, client_id: str = "iliashhn", path: Path | None = None) -> Path:
        path = path or (self.config_dir / "config.toml")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'base_url = "{base_url or self.world.ilias_base}"\nclient_id = "{client_id}"\n', encoding="utf-8")
        return path

    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(STRIP_ENV_PREFIXES) and k not in STRIP_ENV_KEYS}
        env.update({
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
        })
        env["PYTHON_KEYRING_BACKEND"] = (
            "acceptance_keyring.FileKeyring" if self.keyring_mode == "fake" else "keyring.backends.fail.Keyring"
        )
        if self.use_config_dir_env:
            env["ILIAS_CLI_CONFIG_DIR"] = str(self.config_dir)
        return env

    # -- Aufrufe --
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
                start_new_session=True,  # kein Controlling-TTY -> Prompts lesen von stdin
            )
            res = RunResult(tuple(args), proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            res = RunResult(tuple(args), -999, str(exc.stdout or ""), f"TIMEOUT nach {timeout}s\n{exc.stderr or ''}")
        self.runs.append(res)
        return res

    def login(self, *extra: str, password: str = PASSWORD, totp: str = TOTP, username: str = USERNAME) -> RunResult:
        return self.run("login", *extra, input=f"{username}\n{password}\n{totp}\n")

    # -- Inspektion --
    def written_files(self) -> list[Path]:
        """Alle Dateien, die das Tool geschrieben haben könnte (ohne die vom Test geschriebene config.toml)."""
        out = []
        for base in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            for p in base.rglob("*"):
                if p.is_file() and p.name != "config.toml":
                    out.append(p)
        return out

    def files_containing(self, needle: str) -> list[Path]:
        hits = []
        for p in self.written_files():
            try:
                if needle.encode() in p.read_bytes():
                    hits.append(p)
            except OSError:
                pass
        return hits

    def session_artifacts(self) -> list[Path]:
        """Dateien, die eine vom Fake-ILIAS ausgegebene Session-ID enthalten."""
        hits: set[Path] = set()
        for sid in self.world.issued_session_ids:
            hits.update(self.files_containing(sid))
        return sorted(hits)

    def all_output(self) -> str:
        return "\n".join(r.stdout + "\n" + r.stderr for r in self.runs)


@pytest.fixture
def world():
    w = FakeWorld(username=USERNAME, password=PASSWORD, totp=TOTP).start()
    yield w
    w.stop()


@pytest.fixture
def h(tmp_path, world) -> Harness:
    return Harness(tmp_path, world)


def file_mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)
