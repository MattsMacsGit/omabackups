"""Wi-Fi on the Rescue USB (D47): iwd, as on Omarchy's installer. Only asked
when there's no working network (a cable just works: systemd-networkd).
"""

import re
import subprocess
import time
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SECURITY = {"psk", "open", "8021x", "wep", "sae", "owe"}


def online() -> bool:
    """A default route: a cable or a Wi-Fi that's connected."""
    done = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
    return bool(done.stdout.strip())


def device() -> str | None:
    for p in sorted(Path("/sys/class/net").glob("*")):
        if (p / "wireless").is_dir() or (p / "phy80211").exists():
            return p.name
    return None


def _iwctl(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["iwctl", *args], capture_output=True, text=True, timeout=timeout)


def parse_networks(text: str) -> list[dict]:
    """iwctl's table of networks: name (spaces allowed), security, signal."""
    out = []
    for raw in ANSI.sub("", text).splitlines():
        line = raw.strip().lstrip(">").strip()
        parts = line.split()
        if len(parts) < 3 or parts[-2] not in SECURITY:
            continue
        name = line[: line.rfind(parts[-2])].strip()
        if name:
            out.append({"name": name, "security": parts[-2], "signal": parts[-1]})
    return out


def networks(dev: str) -> list[dict]:
    _iwctl("station", dev, "scan")
    time.sleep(3)
    return parse_networks(_iwctl("station", dev, "get-networks").stdout)


def connect(dev: str, name: str, password: str) -> str:
    """'' when connected, else what went wrong."""
    args = (["--passphrase", password] if password else []) + ["station", dev, "connect", name]
    done = _iwctl(*args, timeout=60)
    if done.returncode != 0:
        return ANSI.sub("", done.stderr or done.stdout).strip() or "it didn't connect"
    for _ in range(20):
        if online():
            return ""
        time.sleep(1)
    return "connected, but no network address came"
