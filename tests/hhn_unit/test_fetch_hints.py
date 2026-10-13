"""Fehler-Hinweise von ``Fetcher`` nennen nur im CLI vorhandene Befehle (Issue #40)."""

from __future__ import annotations

import pytest

from ilias_core.config import Config
from ilias_core.errors import NotLoggedInError, SessionExpiredError
from ilias_core.ilias_html.fetch import Fetcher


class _EmptyStore:
    def load(self):
        return {}


def test_not_logged_in_hint_mentions_login_not_setup():
    config = Config(base_url="https://ilias.example.org", instance="hhn")
    with pytest.raises(NotLoggedInError) as excinfo:
        Fetcher(config, _EmptyStore())
    hint = excinfo.value.hint or ""
    assert "ilias login" in hint
    assert "setup" not in hint.lower()


def test_session_expired_hint_mentions_login_not_setup():
    fetcher = object.__new__(Fetcher)
    fetcher.key = "hhn"
    err = fetcher._session_expired("Kursseite")
    assert isinstance(err, SessionExpiredError)
    hint = err.hint or ""
    assert "ilias login" in hint
    assert "setup" not in hint.lower()
