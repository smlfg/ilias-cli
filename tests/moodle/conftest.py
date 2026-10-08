"""Pytest-Fixtures für Moodle-Tests.

Startet einen lokalen Fake-Moodle-Server und konfiguriert die CLI,
diese gegen localhost zu verwenden. Tests dürfen nur localhost kontaktieren.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import shutil
from pathlib import Path

import pytest

from .fake_server import MoodleFakeWorld, file_mode, free_port


def _ilias_executable() -> str:
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


# ---- Fixture: fake Moodle server -------------------------------------------

@pytest.fixture
def world():
    w = MoodleFakeWorld(username=USERNAME, password=PASSWORD).start()
    yield w
    w.stop()


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Verzeichnis für die Test-Konfiguration (Keyring/Dateien)."""
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    return cfg


# ---- Fixture: ilias CLI runner --------------------------------------------

@pytest.fixture
def h(tmp_path: Path, world: MoodleFakeWorld, config_dir: Path) -> "Harness":
    """Harness, das den Fake-Moodle-Server nutzt."""

    # Write config pointing to the fake server
    config_path = config_dir / "config.toml"
    config_path.write_text(
        f'base_url = "http://127.0.0.1:{world.port}"\nlms = "moodle"\ninstance = "hs-mannheim"\n',
        encoding="utf-8",
    )

    # Determine ilias executable
    ilias_bin = _ilias_executable()

    # HOME for subprocess
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------
    # Harness-Klasse
    # -----------------------------------------------------------------
    class Harness:
        def __init__(self, tmp_path: Path, world: MoodleFakeWorld, config_dir: Path, ilias_bin: str) -> None:
            self.world = world
            self.root = tmp_path
            self.home = home_dir
            self.config_dir = config_dir
            self.keyring_file = tmp_path / "keyring" / "keyring.json"
            self.net_log = tmp_path / "net-blocked.log"
            self.cwd = tmp_path / "work"
            for d in (self.home, self.config_dir, self.cwd, self.keyring_file.parent):
                d.mkdir(parents=True, exist_ok=True)
            self.keyring_mode = "fake"
            self.runs: list[dict] = []
            self.ilias_bin = ilias_bin
            self._ilias_cfg_written = False

        def _write_config(self) -> None:
            if self._ilias_cfg_written:
                return
            config_path = self.config_dir / "config.toml"
            config_path.write_text(
                f'base_url = "http://127.0.0.1:{self.world.port}"\nlms = "moodle"\ninstance = "hs-mannheim"\n',
                encoding="utf-8",
            )
            self._ilias_cfg_written = True

        def env(self) -> dict[str, str]:
            # Strip env vars that could point to external networks
            prefixes = ("ILIAS_", "PYTHON_KEYRING", "XDG_", "KEYRING_")
            keys_to_block = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
            env = {
                k: v for k, v in os.environ.items()
                if not any(k.startswith(p) for p in prefixes) and k not in keys_to_block
            }
            env.update({
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "NO_COLOR": "1",
                "TERM": "dumb",
                "COLUMNS": "200",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONPATH": str(Path(__file__).parent.parent / "acceptance" / "support"),
                "ACCEPTANCE_KEYRING_FILE": str(self.keyring_file),
                "ACCEPTANCE_SANDBOX": "1",
                "ACCEPTANCE_NET_LOG": str(self.net_log),
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
            })
            env["PYTHON_KEYRING_BACKEND"] = (
                "acceptance_keyring.FileKeyring" if self.keyring_mode == "fake" else "keyring.backends.fail.Keyring"
            )
            # ILIAS_CLI_CONFIG_DIR must point to our config dir
            env["ILIAS_CLI_CONFIG_DIR"] = str(self.config_dir)
            return env

        def run(self, *args: str, input: str | None = None, timeout: float = 60) -> dict:
            try:
                proc = subprocess.run(
                    [self.ilias_bin, *args],
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
                result = {
                    "args": args,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                }
            except subprocess.TimeoutExpired as exc:
                result = {
                    "args": args,
                    "exit_code": -999,
                    "stdout": str(exc.stdout or ""),
                    "stderr": f"TIMEOUT nach {timeout}s\n{exc.stderr or ''}",
                }
            self.runs.append(result)
            return result

        def login(self, *extra: str, password: str = PASSWORD, username: str = USERNAME) -> dict:
            # Moodle login flow: prompt for username then password via stdin
            inp = f"{username}\n{password}\n"
            return self.run("login", *extra, input=inp)

        # -- Inspektion --
        def written_files(self) -> list[Path]:
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
            # Moodle stores token, not ILIAS session cookies
            return []

        def all_output(self) -> str:
            return "\n".join(r["stdout"] + "\n" + r["stderr"] for r in self.runs)

        def assert_no_external_network(self) -> None:
            if self.net_log.exists() and self.net_log.read_text().strip():
                pytest.fail("Netzwerkzugriff außerhalb von localhost versucht (blockiert):\n" + self.net_log.read_text())

    harness = Harness(tmp_path, world, config_dir, ilias_bin)
    # Write config immediately so it's available on first run
    harness._write_config()
    yield harness
    # Nach dem Test: sicherstellen, dass kein externer Netzwerkzugriff stattfand
    harness.assert_no_external_network()