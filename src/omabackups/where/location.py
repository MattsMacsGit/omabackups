"""Where this computer's backup is: connect to it, server or disk."""

import json

from omabackups.core import paths
from omabackups.core.errors import OmaError


def load() -> dict:
    try:
        return json.loads(paths.server_file().read_text())
    except (OSError, ValueError):
        raise OmaError("No backup location is set up on this computer.",
                       "Set up backups first.", code="not-set-up") from None


def connect(server: dict):
    """(the gatekeeper to talk to, away from home?)."""
    if server.get("kind") == "disk":
        from omabackups.where import disk
        disk.present(server)
        return disk.LocalGate(paths.public_key_file().read_text()), False
    from omabackups.where import network
    from omabackups.where.server import Gate
    address, away = network.route(server)
    return Gate(address), away
