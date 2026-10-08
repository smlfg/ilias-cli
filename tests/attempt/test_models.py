"""Tests for models module."""

import json

from ilias_core.models import SessionCookies, LoginResult, SessionStatus, LogoutResult


def test_session_cookies_to_dict() -> None:
    """Test SessionCookies serialization."""
    cookies = SessionCookies(
        phpsessid="abc123",
        il_client_id="def456",
        extra={"custom": "value"},
    )
    data = cookies.to_dict()
    assert data == {
        "PHPSESSID": "abc123",
        "ilClientId": "def456",
        "custom": "value",
    }


def test_session_cookies_from_dict() -> None:
    """Test SessionCookies deserialization."""
    data = {
        "PHPSESSID": "abc123",
        "ilClientId": "def456",
        "custom": "value",
    }
    cookies = SessionCookies.from_dict(data)
    assert cookies.phpsessid == "abc123"
    assert cookies.il_client_id == "def456"
    assert cookies.extra == {"custom": "value"}


def test_session_cookies_get_cookie_header() -> None:
    """Test cookie header generation."""
    cookies = SessionCookies(
        phpsessid="abc123",
        il_client_id="def456",
        extra={"custom": "value"},
    )
    header = cookies.get_cookie_header()
    assert "PHPSESSID=abc123" in header
    assert "ilClientId=def456" in header
    assert "custom=value" in header


def test_login_result_json_excludes_cookies() -> None:
    """Test LoginResult JSON output excludes cookies."""
    cookies = SessionCookies(phpsessid="secret", il_client_id="secret2")
    result = LoginResult(success=True, message="OK", cookies=cookies)

    json_str = result.model_dump_json(exclude={"cookies"})
    data = json.loads(json_str)

    assert data["success"] is True
    assert data["message"] == "OK"
    assert "cookies" not in data


def test_session_status_json() -> None:
    """Test SessionStatus JSON output."""
    status = SessionStatus(
        logged_in=True,
        message="OK",
        username="testuser",
        expires_at="2026-10-07T12:00:00+02:00",
    )
    json_str = status.model_dump_json()
    data = json.loads(json_str)

    assert data["logged_in"] is True
    assert data["username"] == "testuser"
    assert data["expires_at"] == "2026-10-07T12:00:00+02:00"


def test_logout_result_json() -> None:
    """Test LogoutResult JSON output."""
    result = LogoutResult(success=True, message="Logged out")
    json_str = result.model_dump_json()
    data = json.loads(json_str)

    assert data["success"] is True
    assert data["message"] == "Logged out"