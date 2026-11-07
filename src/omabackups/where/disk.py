"""A backup disk plugged into this computer (BUILD 5.1 where/disk.py).

The same gatekeeper as on a server runs right here, as root, in local mode
(`gate.pyz direct`): same verbs, same layout, same holds. Only the way in
differs: no SSH, no socket.
"""

import base64
import hashlib
import os
import shlex
import sys
from pathlib import Path

from omabackups.core.errors import OmaError
from omabackups.setup import bundle
from omabackups.where.server import Gate


def key_id(public_key: str) -> str:
    """The gatekeeper's name for a key (as its registry works it out)."""
    return hashlib.sha256(base64.b64decode(public_key.split()[1])).hexdigest()[:16]


def local_env() -> dict:
    return dict(os.environ, OMABACKUPS_GATE_LOCAL="1")


class LocalGate(Gate):
    def __init__(self, public_key: str):
        super().__init__("local")
        self.kid = key_id(public_key)
        self.gate = str(bundle.gate_file())

    def _argv(self, command: str):
        return ([sys.executable, self.gate, "direct", self.kid],
                {**local_env(), "SSH_ORIGINAL_COMMAND": command})

    def rsh(self) -> str:
        return shlex.join([sys.executable, self.gate, "direct-rsh", self.kid])

    def rsync_env(self) -> dict:
        return local_env()

    def rsync_target(self) -> str:
        return "local"

    def call(self, verb: str, *args: str, data: bytes = b"") -> dict:
        if verb == "lock" and len(args) == 2:
            # A disk on this computer locks as soon as the job is done: there's
            # no slow unlock to save (the server's quiet time is for a Pi).
            args = args[:1]
        return super().call(verb, *args, data=data)


def present(server: dict) -> None:
    if not Path(server["device"]).exists():
        raise OmaError("Your backup disk isn't plugged in.",
                       "Plug it in: the next backup runs by itself (or Back up now).",
                       server["device"], code="unreachable")
