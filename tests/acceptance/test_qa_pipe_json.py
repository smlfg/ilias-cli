"""Regressionstest zu QA-FAIL 1: JSON bei Pipe/Nicht-TTY-stdout.

INTERFACE.md §2: Ohne ``--json`` liefert ein Nicht-TTY-stdout (Pipe/Agent) JSON.
"""

from __future__ import annotations

from .conftest import Harness


def test_status_without_json_in_pipe_is_json(h: Harness):
    assert h.login().exit_code == 0
    result = h.run("status")
    assert result.exit_code == 0, str(result)
    data = result.json()
    assert data["authenticated"] is True
