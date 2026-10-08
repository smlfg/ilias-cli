"""Exception hierarchy for ILIAS CLI, mapping to exit codes."""


class ILIASError(Exception):
    """Base exception for all ILIAS CLI errors."""

    exit_code: int = 1

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause

    def __str__(self) -> str:
        return self.message


class NetworkError(ILIASError):
    """Network or server error (exit code 4)."""

    exit_code = 4


class ParserError(ILIASError):
    """HTML parsing error / unexpected page structure (exit code 5)."""

    exit_code = 5


class NotLoggedInError(ILIASError):
    """No valid session found (exit code 2)."""

    exit_code = 2


class SessionExpiredError(ILIASError):
    """Session exists but has expired (exit code 3)."""

    exit_code = 3


class InvalidCredentialsError(ILIASError):
    """Invalid username/password provided."""

    exit_code = 1


class InvalidTOTPError(ILIASError):
    """Invalid TOTP code provided."""

    exit_code = 1


class BrowserNotAvailableError(ILIASError):
    """Playwright browser not available for fallback login."""

    exit_code = 1


class ConfigurationError(ILIASError):
    """Configuration error."""

    exit_code = 1


# Map exit codes to exception classes for easy lookup
EXIT_CODE_MAP = {
    0: None,  # Success
    1: ILIASError,
    2: NotLoggedInError,
    3: SessionExpiredError,
    4: NetworkError,
    5: ParserError,
}


def exit_code_for_error(error: Exception) -> int:
    """Get exit code for an exception."""
    if isinstance(error, ILIASError):
        return error.exit_code
    return 1