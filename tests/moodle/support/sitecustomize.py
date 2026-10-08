"""Automatisch geladen im CLI-Subprozess (PYTHONPATH zeigt auf dieses Verzeichnis).

Blockiert alles außer Loopback und protokolliert jeden Versuch nach
$MOODLE_NET_LOG, damit der Test fehlschlägt (siehe INTERFACE.md §7).
"""

from __future__ import annotations

import os

from guard import install

_LOG = os.environ.get("MOODLE_NET_LOG")


def _record(what: str) -> None:
    if not _LOG:
        return
    try:
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(what + "\n")
    except OSError:
        pass


if os.environ.get("MOODLE_SANDBOX") == "1":
    install(_record)
