"""Authentifizierung gegen Keycloak / OIDC im Browser-Flow."""

from .flow import KeycloakLoginFlow
from .parsers import (
    HtmlForm,
    extract_keycloak_error,
    is_ilias_login_page,
    is_keycloak_login,
    is_keycloak_totp,
    parse_keycloak_login,
    parse_keycloak_totp,
)

__all__ = [
    "KeycloakLoginFlow",
    "HtmlForm",
    "extract_keycloak_error",
    "is_ilias_login_page",
    "is_keycloak_login",
    "is_keycloak_totp",
    "parse_keycloak_login",
    "parse_keycloak_totp",
]
