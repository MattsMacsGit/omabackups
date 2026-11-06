"""This system's ID. Never its hostname (BUILD 8.3 #7: every fresh Omarchy is
called "omarchy", so 1.x's hostname-named keys collided).

The ID is worked out from /etc/machine-id, the way systemd recommends for apps
(an HMAC with an app key), so:
- every install gets its own ID, with nothing to store or lose;
- the raw machine-id never leaves the computer;
- a system brought back by a rescue keeps its ID (machine-id comes back too),
  while a fresh install that Migrates gets a new one (the handover, D22).
"""

import hashlib
import hmac
import re

from omabackups.core import paths
from omabackups.core.errors import OmaError

# Fixed forever: changing it would give every system a new ID.
_APP_KEY = bytes.fromhex("6f6d616261636b7570732d73797374656d")  # "omabackups-system"

_MACHINE_ID = re.compile(r"^[0-9a-f]{32}$")


def system_id() -> str:
    """32 hex characters that name this system to its backup."""
    path = paths.machine_id_file()
    try:
        machine = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise _no_id(path, str(exc)) from exc
    if not _MACHINE_ID.match(machine):
        raise _no_id(path, "it doesn't hold a machine ID")
    return hmac.new(bytes.fromhex(machine), _APP_KEY, hashlib.sha256).hexdigest()[:32]


def short(system: str) -> str:
    """The first 8 characters: enough for people to tell systems apart."""
    return system[:8]


def _no_id(path, why: str) -> OmaError:
    return OmaError(
        "OmaBackups can't tell which computer this is.",
        "This computer's machine ID is missing. Running "
        "'systemd-machine-id-setup' as root makes a new one.",
        f"{path}: {why}",
        code="no-system-id",
    )
