"""The gatekeeper's fixed names and places (BUILD 5.3).

Runs on the backup server, on its own Python (3.11 or newer, standard
library only). All names are `omabackups-gate`, so it never touches 1.x's
`omabackups` account or files (D23).

Test mode: only when NOT running as root, OMABACKUPS_GATE_ROOT moves every
path under a test folder and boxes become plain folders (fakehost.py). As
root these are ignored, so the real service can't be pointed elsewhere.
"""

import os
import re
from pathlib import Path

VERSION = 3          # the gatekeeper's own version (2.0 started at 1; 2: data verbs; 3: addresses)
CONTRACT = 1         # the version of its verbs and answers (BUILD 5.10)
ACCOUNT = "omabackups-gate"

TEST = os.geteuid() != 0 and bool(os.environ.get("OMABACKUPS_GATE_ROOT"))


def _p(path: str) -> Path:
    return Path(os.environ["OMABACKUPS_GATE_ROOT"] + path) if TEST else Path(path)


SETTINGS = _p("/etc/omabackups-gate/gate.json")        # where the backup store is
REGISTRY = _p("/var/lib/omabackups-gate/registry.json")  # keys, backups, roles
HOME = _p("/var/lib/omabackups-gate/home")               # the account's home (root-owned)
AUTHORIZED_KEYS = HOME / ".ssh" / "authorized_keys"
RUN = _p("/run/omabackups-gate")                         # locks, holds, mount points
SOCKET = RUN / "gate.sock"
INSTALLED = Path("/usr/lib/omabackups-gate/gate.pyz")    # where setup puts this file

# Names the outside world can send us: checked before any use.
BACKUP_ID = re.compile(r"^[0-9a-f]{32}$")
KEY_ID = re.compile(r"^[0-9a-f]{16}$")
SYSTEM_ID = re.compile(r"^[0-9a-f]{32}$")
HOLD_ID = re.compile(r"^[0-9a-f]{16}$")
POINT = re.compile(r"^\d{3}-\d{4}-\d{2}-\d{2}-\d{4}$")    # <line>-<date>-<time> (D22a)
PUBKEY = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/]+={0,2}$")
LABEL = re.compile(r"^[A-Za-z0-9 ._()-]{1,64}$")

MAX_SECRET = 8192          # a password or key file, in bytes
MAX_REQUEST = 64 * 1024    # the first line of a request

HOLD_STALE = 600   # a hold nothing refreshes for this long belongs to something dead
IDLE_LOCK = 600    # with no holds, a backup locks after this long with no disk activity
MIN_BOX = 1 << 30  # the smallest backup box: 1 GiB

ROLES = ("owner", "rescue")
