"""Home or away (D17), found automatically.

Home: the backup server answers at the address it was set up with (on your
local network). Away: it doesn't, but answers at one of its Tailscale
addresses (learnt from the gatekeeper whenever you're home). Neither: your
backup can't be reached. The server's host key is checked the same way at
every address (ssh.py's HostKeyAlias).
"""

import ipaddress
import json
import os
import socket

from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic

HOME_WAIT = 3     # seconds to wait for the home address
AWAY_WAIT = 8


def answers(address: str, wait: float) -> bool:
    if os.environ.get("OMABACKUPS_SYSROOT"):      # tests: no network
        return address in os.environ.get("OMABACKUPS_TEST_REACHABLE", "test").split(",")
    try:
        with socket.create_connection((address, 22), timeout=wait):
            return True
    except OSError:
        return False


def route(server: dict) -> tuple[str, bool]:
    """(the address to use, away?)."""
    if answers(server["address"], HOME_WAIT):
        return server["address"], False
    for address in server.get("away", []):
        if answers(address, AWAY_WAIT):
            log.get("network").info("away from home: using %s", address)
            return address, True
    raise OmaError("Your backup can't be reached.",
                   "Check the network (and Tailscale, if you're away from home). The next "
                   "backup tries again by itself.",
                   f"tried {server['address']} and {', '.join(server.get('away', [])) or 'no away address'}",
                   code="unreachable")


def learn_away_addresses(gate, server: dict) -> None:
    """While home: remember how to reach the server from elsewhere (Tailscale)."""
    try:
        if gate.call("version").get("gate", 0) < 3:
            return
        found = gate.call("addresses")
    except OmaError:
        return
    ts = found.get("tailscale") or {}
    away = [a for a in [ts.get("name", ""), *ts.get("ips", [])] if a and _usable(a)]
    if away and away != server.get("away"):
        server["away"] = away
        write_atomic(paths.server_file(), (json.dumps(server, indent=2) + "\n").encode(), 0o644)


def _usable(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
        return not (ip.is_loopback or ip.is_link_local)
    except ValueError:
        return all(part.replace("-", "").isalnum() for part in address.split("."))
