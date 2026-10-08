"""Harness für die HHN-Tests (F2/F3 für ILIAS per HTML, `ilias setup`), siehe docs/HHN_2FA_SPEC.md.

Gleiche Regeln wie tests/acceptance: `ilias` als Subprozess, Netzwerk-Sandbox (nur
localhost), Fake-Keyring, nur synthetische Daten.

Solange die Befehle noch nicht gebaut sind, werden alle Tests dieses Ordners als
`xfail` (nicht strikt) markiert, damit die CI auf `main` nicht rot wird. Bau-Modelle
und Reviewer setzen `HHN_STRICT=1`, dann zählen die Tests hart:

    HHN_STRICT=1 uv run pytest tests/hhn -q
"""

from __future__ import annotations

import os

import pytest
from acceptance.conftest import (
    PASSWORD,
    TOTP,
    USERNAME,
    Harness,
    assert_no_external_network,
)

from .fake_hhn import HhnWorld

__all__ = ["PASSWORD", "TOTP", "USERNAME", "HhnHarness"]


def pytest_collection_modifyitems(config, items):
    if os.environ.get("HHN_STRICT") == "1":
        return
    marker = pytest.mark.xfail(reason="HHN-Spec: noch nicht implementiert (HHN_STRICT=1 für harte Prüfung)", strict=False)
    # Nur Tests in tests/hhn/ selbst: os.sep anhängen, sonst passt das Präfix auch auf
    # Geschwister-Ordner wie tests/hhn_unit/ (die würden still als xfail markiert).
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
    for item in items:
        if os.path.abspath(str(item.fspath)).startswith(here):
            item.add_marker(marker)


class HhnHarness(Harness):
    """Wie die Akzeptanz-Harness, aber ohne künstliche Wartezeit zwischen Requests (Spec N2)."""

    def env(self) -> dict[str, str]:
        env = super().env()
        env["ILIAS_CLI_REQUEST_INTERVAL"] = "0"
        return env

    def setup(self, *extra: str, input: str) -> object:
        return self.run("setup", *extra, input=input)

    def kc_posts(self) -> list:
        return [r for r in self.world.requests_to("keycloak") if r.method == "POST"]

    def otp_posts(self) -> list:
        return [r for r in self.kc_posts() if "otp" in r.form]

    def password_posts(self) -> list:
        return [r for r in self.kc_posts() if "password" in r.form]


@pytest.fixture
def hworld():
    w = HhnWorld(username=USERNAME, password=PASSWORD, totp=TOTP).start()
    yield w
    w.stop()


@pytest.fixture
def hh(tmp_path, hworld) -> HhnHarness:
    harness = HhnHarness(tmp_path, hworld)
    yield harness
    assert_no_external_network(harness)


@pytest.fixture
def logged_in(hh: HhnHarness) -> HhnHarness:
    r = hh.login()
    assert r.exit_code == 0, str(r)
    return hh
