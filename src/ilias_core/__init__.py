"""ilias_core: shared core library (auth, session, config, models, errors)."""

__version__ = "0.1.0"

USER_AGENT = f"ilias-cli/{__version__}"

DEFAULT_BASE_URL = "https://ilias.hs-heilbronn.de"
DEFAULT_CLIENT_ID = "iliashhn"

REQUEST_TIMEOUT = 15.0
