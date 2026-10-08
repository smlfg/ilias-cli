class IliasCliError(Exception):
    exit_code = 1

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotLoggedInError(IliasCliError):
    exit_code = 2


class SessionExpiredError(IliasCliError):
    exit_code = 3


class NetworkError(IliasCliError):
    exit_code = 4


class ParserError(IliasCliError):
    exit_code = 5


class AuthError(IliasCliError):
    exit_code = 1


class BrowserUnavailableError(IliasCliError):
    exit_code = 1
