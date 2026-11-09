"""Services and their settings, as 1.x's Migrate handled them (D41).

A setting in a system folder that a service uses while it runs goes in with
that service stopped, then the service comes back as the old system had it:
switched on if it was on there, and started. The network managers are never
stopped (that would drop the network): they're told to reload instead.
Which services the old system had on comes from its restore point: every
`*.wants` link in its /etc/systemd/system.

Pure: nothing here changes anything.
"""

from pathlib import Path

# A system folder an app uses while it runs -> its service (1.x list).
# Longest match wins.
SERVICES = {
    "/var/lib/tailscale": "tailscaled",
    "/var/lib/bluetooth": "bluetooth",
    "/var/lib/iwd": "iwd",
    "/etc/NetworkManager": "NetworkManager",
    "/var/lib/fprint": "fprintd",
    "/var/lib/ollama": "ollama",
    "/var/lib/nordvpn": "nordvpnd",
    "/etc/cups": "cups",
    "/var/lib/docker": "docker",
}
# Never stopped: they reload (1.x). Stopping one cuts the network.
LIVE = {"NetworkManager", "iwd"}
UNITS = (".service", ".socket", ".timer", ".path")


def service_for(path: str) -> str | None:
    """The service a system path belongs to, if any."""
    path = "/" + path.lstrip("/")
    best = ""
    for prefix in SERVICES:
        if (path == prefix or path.startswith(prefix + "/")) and len(prefix) > len(best):
            best = prefix
    return SERVICES.get(best)


def enabled(systemd_dir: Path) -> set[str]:
    """The units switched on in a copy of /etc/systemd/system: the names in
    every *.wants (and *.requires) folder."""
    out = set()
    if not systemd_dir.is_dir():
        return out
    for wants in systemd_dir.iterdir():
        if wants.is_dir() and wants.name.endswith((".wants", ".requires")):
            out |= {e.name for e in wants.iterdir() if e.name.endswith(UNITS)}
    return out


def was_on(service: str, on: set[str]) -> bool:
    """Was this service switched on in the old system? (its .service or its
    socket: some services start from a socket)."""
    return f"{service}.service" in on or f"{service}.socket" in on


def split(system_items: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """System settings: those that go straight into place, and those that go
    in with their service stopped (service -> its items)."""
    plain, held = [], {}
    for item in system_items:
        svc = service_for(item)
        if svc:
            held.setdefault(svc, []).append(item)
        else:
            plain.append(item)
    return plain, held
