"""ilias_core: Kernbibliothek der ILIAS-CLI.

Enthält ALLE Logik (Config, Auth, Session, Modelle, Errors). Weder die
CLI noch ein MCP-Server dürfen eigene Logik enthalten; sie nutzen dieses
Paket. Kernfunktionen machen nie selbst Prompts oder prints - Passwort
und TOTP werden als Parameter bzw. Callback übergeben.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ilias-cli")
except PackageNotFoundError:  # pragma: no cover - nicht installiert
    __version__ = "0.0.0"

__all__ = ["__version__"]
