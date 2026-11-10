"""Finding the backup server, by name or address, at home or away (D17, D48).

What was typed at setup can be an address, the server's name, name.local or
its Tailscale name. Every time the server is reached it says where it is
(the gatekeeper's `addresses`), and those are remembered (1.x: a new address
from the router never sends backups down the tunnel). The order tried:

  1. its home addresses (learnt), and what was typed if it isn't Tailscale
  2. name.local (mDNS), if a bare name was typed
  3. its Tailscale name and addresses: away

Only a Tailscale route counts as away (the size limit, D17). The server's
host key is checked the same way at every address (ssh.py's HostKeyAlias).
The Rescue USB carries the same list and tries the same order (no limit).
"""

import ipaddress
import json
import os
import socket

from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic

HOME_WAIT = 3     # seconds to wait for a home address
AWAY_WAIT = 8
TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


def answers(address: str, wait: float) -> bool:
    if os.environ.get("OMABACKUPS_SYSROOT"):      # tests: no network
        return address in os.environ.get("OMABACKUPS_TEST_REACHABLE", "test").split(",")
    try:
        with socket.create_connection((address, 22), timeout=wait):
            return True
    except OSError:
        return False


def _ip(address: str):
    try:
        return ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return None


def tailscale(address: str) -> bool:
    """Reached through Tailscale: its addresses, a *.ts.net name, or a name
    Tailscale's DNS answers with one of its addresses (a bare name often is:
    MagicDNS's search domain)."""
    ip = _ip(address)
    if ip is not None:
        return any(ip in net for net in TAILNET)
    if address.rstrip(".").endswith(".ts.net"):
        return True
    if os.environ.get("OMABACKUPS_SYSROOT"):      # tests: no name lookups
        return False
    try:
        found = {_ip(i[4][0]) for i in socket.getaddrinfo(address, 22, proto=socket.IPPROTO_TCP)}
    except OSError:
        return False
    return bool(found) and all(f is not None and any(f in net for net in TAILNET) for f in found)


def _bare_name(address: str) -> bool:
    return _ip(address) is None and "." not in address.rstrip(".")


def candidates(server: dict) -> list[tuple[str, bool]]:
    """(address, away?) in the order to try them."""
    typed = server["address"]
    typed_away = tailscale(typed)
    home = list(server.get("home", [])) + ([] if typed_away else [typed])
    if _bare_name(typed):
        home.append(f"{typed}.local")
    away = list(server.get("away", [])) + ([typed] if typed_away else [])
    out, seen = [], set()
    for address, is_away in [(a, False) for a in home] + [(a, True) for a in away]:
        if address and address not in seen:
            seen.add(address)
            out.append((address, is_away))
    return out


def route(server: dict) -> tuple[str, bool]:
    """(the address to use, away?)."""
    tried = candidates(server)
    for address, away in tried:
        if answers(address, AWAY_WAIT if away else HOME_WAIT):
            if away:
                log.get("network").info("away from home: using %s", address)
            return address, away
    raise OmaError("Your backup can't be reached.",
                   "Check the network (and Tailscale, if you're away from home). The next "
                   "backup tries again by itself.",
                   "tried " + (", ".join(a for a, _ in tried) or "no address"), code="unreachable")


def learn_addresses(gate, server: dict) -> None:
    """Whenever the server is reached: remember where it is now, at home and
    on Tailscale (D48)."""
    try:
        if gate.call("version").get("gate", 0) < 3:
            return
        found = gate.call("addresses")
    except OmaError:
        return
    home, away = split(found)
    changed = False
    for key, value in (("home", home), ("away", away)):
        if value and value != server.get(key):
            server[key] = value
            changed = True
    if changed:
        write_atomic(paths.server_file(), (json.dumps(server, indent=2) + "\n").encode(), 0o644)


learn_away_addresses = learn_addresses      # the name before D48


def split(found: dict) -> tuple[list[str], list[str]]:
    """The gatekeeper's answer as (home addresses, IPv4 first; away: Tailscale name and addresses)."""
    home = []
    for a in found.get("addresses", []):
        ip = _ip(a)
        if ip is None or ip.is_loopback or ip.is_link_local or any(ip in net for net in TAILNET):
            continue
        home.append(str(ip))
    home.sort(key=lambda a: (_ip(a).version, a))
    ts = found.get("tailscale") or {}
    away = [a for a in [ts.get("name", ""), *ts.get("ips", [])] if a and _usable(a)]
    return home, away


def _usable(address: str) -> bool:
    ip = _ip(address)
    if ip is not None:
        return not (ip.is_loopback or ip.is_link_local)
    return all(part.replace("-", "").isalnum() for part in address.rstrip(".").split("."))
