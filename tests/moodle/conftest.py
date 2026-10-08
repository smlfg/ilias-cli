"""Harness für die Moodle-Tests.

Getestet wird ausschließlich über die öffentliche Schnittstelle: das installierte
Kommando `ilias` als Subprozess, Konfiguration über `ILIAS_CLI_CONFIG_DIR` +
config.toml, HTTP gegen einen lokalen Fake-Moodle (`fake_moodle.py`).

Zwei Sicherungen gegen echte Netzwerkzugriffe:
* `sitecustomize.py` im PYTHONPATH des Subprozesses blockiert alles außer Loopback,
* die Fixture `no_external_network` (autouse) installiert denselben Guard im
  pytest-Prozess und lässt den Test bei jedem Versuch fehlschlagen.
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

TESTS_DIR = Path(__file__).resolve().parent
SUPPORT_DIR = TESTS_DIR / "support"
sys.path.insert(0, str(TESTS_DIR))  # acceptance.leak_check wiederverwenden
sys.path.insert(0, str(SUPPORT_DIR))  # guard.py

USERNAME = "hs.mannheim.student"
PASSWORD = "M00dle-Geheim-7Qx!2026"  # nur für Tests, nie eine echte Zugangsberechtigung
INSTANCE = "hs-mannheim"
STRIP_ENV_PREFIXES = ("ILIAS_", "PYTHON_KEYRING", "XDG_", "KEYRING_", "MOODLE_")
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
        pytest.fail("Kommando `ilias` nicht gefunden (uv sync ausführen oder ILIAS_BIN setzen)")
    return found


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def file_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@dataclass
class RunResult:
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    def json(self, strict: bool = True):
        """JSON aus stdout (strict=False erlaubt Prompt-Text davor)."""
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
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "config"
        self.keyring_file = tmp_path / "keyring" / "keyring.json"
        self.net_log = tmp_path / "net-blocked.log"
        self.cwd = tmp_path / "work"
        for directory in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            directory.mkdir(parents=True, exist_ok=True)
        self.keyring_mode = "fake"  # fake | none
        self.runs: list[RunResult] = []
        self.write_config()

    # -- Konfiguration ---------------------------------------------------
    def write_config(self, base_url: str | None = None, instance: str = INSTANCE, lms: str = "moodle") -> Path:
        """config.toml mit eingebautem Profil-Key; base_url zeigt auf den Fake-Server."""
        path = self.config_dir / "config.toml"
        path.write_text(
            f'instance = "{instance}"\n\n'
            f"[instances.{instance}]\n"
            f'lms = "{lms}"\n'
            f'base_url = "{base_url or self.world.base_url}"\n',
            encoding="utf-8",
        )
        return path

    def remove_config(self) -> None:
        (self.config_dir / "config.toml").unlink(missing_ok=True)

    @property
    def token_file(self) -> Path:
        return self.config_dir / "sessions" / f"{INSTANCE}.json"

    # -- Aufrufe ---------------------------------------------------------
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
                "ILIAS_CLI_CONFIG_DIR": str(self.config_dir),
                "PYTHONPATH": str(SUPPORT_DIR),
                "NO_COLOR": "1",
                "TERM": "dumb",
                "COLUMNS": "200",
                "PYTHONIOENCODING": "utf-8",
                "MOODLE_KEYRING_FILE": str(self.keyring_file),
                "MOODLE_SANDBOX": "1",
                "MOODLE_NET_LOG": str(self.net_log),
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                # toter Proxy als zweite Sicherung
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
            }
        )
        env["PYTHON_KEYRING_BACKEND"] = (
            "moodle_keyring.FileKeyring" if self.keyring_mode == "fake" else "keyring.backends.fail.Keyring"
        )
        return env

    def run(self, *args: str, stdin: str = "", timeout: float = 60) -> RunResult:
        try:
            proc = subprocess.run(
                [ilias_executable(), *args],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.env(),
                cwd=self.cwd,
                timeout=timeout,
                start_new_session=True,  # kein Controlling-TTY -> Eingaben kommen aus stdin
            )
            result = RunResult(tuple(args), proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            result = RunResult(tuple(args), -999, str(exc.stdout or ""), f"TIMEOUT nach {timeout}s")
        self.runs.append(result)
        return result

    def login(self, *extra: str, password: str = PASSWORD, username: str = USERNAME) -> RunResult:
        return self.run("login", *extra, stdin=f"{username}\n{password}\n")

    def status(self, *extra: str) -> RunResult:
        return self.run("status", *extra)

    def logout(self, *extra: str) -> RunResult:
        return self.run("logout", *extra)

    # -- Inspektion ------------------------------------------------------
    def all_output(self) -> str:
        return "\n".join(r.stdout + "\n" + r.stderr for r in self.runs)

    def written_files(self) -> list[Path]:
        """Alle Dateien außer der vom Test geschriebenen config.toml."""
        found = []
        for base in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
            for path in base.rglob("*"):
                if path.is_file() and path.name != "config.toml":
                    found.append(path)
        return found

    def files_containing(self, needle: str) -> list[Path]:
        hits = []
        for path in self.written_files():
            try:
                if needle.encode() in path.read_bytes():
                    hits.append(path)
            except OSError:
                continue
        return hits

    def session_artifacts(self) -> list[Path]:
        """Dateien, die einen vom Fake-Moodle ausgestellten Token enthalten."""
        hits: set[Path] = set()
        for token in self.world.tokens:
            hits.update(self.files_containing(token))
        return sorted(hits)

    def keyring_entries(self) -> dict[str, str]:
        if not self.keyring_file.exists():
            return {}
        return json.loads(self.keyring_file.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ Fixtures
@pytest.fixture
def moodle():
    world = FakeMoodle(username=USERNAME, password=PASSWORD).start()
    yield world
    world.stop()


@pytest.fixture
def h(tmp_path, moodle):
    harness = Harness(tmp_path, moodle)
    yield harness
    # Jeder Versuch des CLI-Subprozesses, einen Nicht-localhost-Host zu
    # kontaktieren, lässt den Test scheitern (support/sitecustomize.py).
    assert_no_external_network(harness)


@pytest.fixture(autouse=True)
def no_external_network(tmp_path):
    """Jeder Verbindungs-/DNS-Versuch außerhalb von Loopback lässt den Test scheitern."""
    import guard

    attempts: list[str] = []
    log = tmp_path / "net-blocked-inprocess.log"
    guard.install(attempts.append)
    try:
        yield attempts
    finally:
        if attempts:
            pytest.fail("Netzwerkzugriff außerhalb von localhost versucht (pytest-Prozess):\n" + "\n".join(attempts))
        if log.exists() and log.read_text(encoding="utf-8").strip():
            pytest.fail("Netzwerkzugriff außerhalb von localhost protokolliert:\n" + log.read_text(encoding="utf-8"))


def assert_no_external_network(harness: Harness) -> None:
    """Wie oben, aber für den Subprozess (Log von support/sitecustomize.py)."""
    if harness.net_log.exists() and harness.net_log.read_text(encoding="utf-8").strip():
        pytest.fail(
            "Netzwerkzugriff außerhalb von localhost versucht (Subprozess, blockiert):\n"
            + harness.net_log.read_text(encoding="utf-8")
        )
