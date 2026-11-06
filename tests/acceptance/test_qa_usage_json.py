"""Regressionstests zu QA-FAIL 2: Usage-Fehler mit ``--json`` sind JSON.

AGENTS.md/INTERFACE.md §2: Auch Usage-/Subparser-Fehler liefern genau ein JSON-Objekt.
"""

from __future__ import annotations

from .conftest import Harness


def test_usage_error_missing_argument_with_json_is_json(h: Harness):
    result = h.run("ls", "--json")
    assert result.exit_code == 2, str(result)
    data = result.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "usage_error"
    assert data["exit_code"] == 2


def test_usage_error_bad_parameter_with_json_is_json(h: Harness):
    result = h.run("ls", "900101", "--depth", "0", "--json")
    assert result.exit_code == 2, str(result)
    data = result.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "usage_error"
    assert data["exit_code"] == 2
