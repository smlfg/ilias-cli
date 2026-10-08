"""Auth: Keycloak/OIDC-Login-Flow, Parser für Keycloak-Formulare."""

from ilias_core.auth.browser import login_with_browser
from ilias_core.auth.flow import login
from ilias_core.auth.parser import (
    LoginForm,
    TotpForm,
    has_login_error,
    has_totp_error,
    is_login_page,
    parse_login_form,
    parse_totp_form,
)

__all__ = [
    "login",
    "login_with_browser",
    "LoginForm",
    "TotpForm",
    "parse_login_form",
    "parse_totp_form",
    "is_login_page",
    "has_login_error",
    "has_totp_error",
]
