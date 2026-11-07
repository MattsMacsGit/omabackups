"""Root jobs for a backup server (stage 2).

create-backup: after `setup server` installed the gatekeeper, make this
computer's backup box there, prove the root key opens it, and only then
record the server as this computer's backup location.
"""

import base64
import json
import re
import time

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.root import keys
from omabackups.where.server import Gate

ADDRESS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:_%-]{0,252}$")
HOST_KEY = re.compile(rf"^{re.escape(paths.SERVER_ALIAS)} (ssh|ecdsa)-[A-Za-z0-9@.-]+ [A-Za-z0-9+/=]+$")
MIN_SIZE = 1 << 30


def _checked(request: dict) -> tuple[str, list[str], int, str]:
    address = str(request.get("address", ""))
    host_keys = request.get("host_keys")
    size = request.get("size")
    password = request.get("password")
    if not ADDRESS.match(address):
        raise OmaError("That server address can't be used.", "Check it and try again.",
                       address, code="bad-request")
    if not isinstance(host_keys, list) or not host_keys or not all(
            isinstance(k, str) and HOST_KEY.match(k) for k in host_keys):
        raise OmaError("The server's identity (host key) is missing.",
                       "Run setup server again.", code="bad-request")
    if not isinstance(size, int) or size < MIN_SIZE:
        raise OmaError("The backup's size must be at least 1 GiB.", code="bad-request")
    if not isinstance(password, str) or not password:
        raise OmaError("Your backup's password is missing.", code="bad-request")
    return address, host_keys, size, password


def create_backup(request: dict) -> dict:
    address, host_keys, size, password = _checked(request)
    write_atomic(paths.known_hosts_file(), ("\n".join(host_keys) + "\n").encode(), 0o644)

    gate = Gate(address)
    version = gate.check_version()
    secrets = json.dumps({"password": password,
                          "key": base64.b64encode(keys.read_unlock_key()).decode()})
    made = gate.call("create", str(size), data=secrets.encode())
    bid = made["id"]

    # Prove the everyday way in works before calling it done.
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    inside = gate.call("points", bid)
    gate.call("lock", bid)
    if inside.get("lines", [{}])[0].get("line") != "001":
        raise OmaError("The new backup on the server doesn't look right.",
                       "Run setup server again.", json.dumps(inside)[:500], code="bad-backup")

    server = {"address": address, "backup": bid, "cipher": made["cipher"], "size": size,
              "gate": version["gate"], "set_up": int(time.time())}
    write_atomic(paths.server_file(), (json.dumps(server, indent=2) + "\n").encode(), 0o644)
    return {"backup": bid, "cipher": made["cipher"], "size": size, "hold_checked": bool(hold)}
