"""Fake systemctl / nmcli / pgrep / omarchy commands for the sandbox: no test
ever touches this computer's real services, processes or desktop.

State lives in the folder named by OMABACKUPS_FAKE (one file per kind):
  calls      every call, one line each ("systemctl stop tailscaled.service")
  units      units this computer has (systemctl cat)
  active     units running now (is-active; start/stop change it)
  enabled    units switched on (enable adds)
  running    process names running as the user (pgrep)
"""

import os
import sys
from pathlib import Path

STATE = Path(os.environ["OMABACKUPS_FAKE"])


def lines(name: str) -> set[str]:
    p = STATE / name
    return set(p.read_text().split()) if p.exists() else set()


def put(name: str, values: set[str]) -> None:
    (STATE / name).write_text("".join(f"{v}\n" for v in sorted(values)))


def systemctl(args: list[str]) -> int:
    args = [a for a in args if a not in ("--no-ask-password", "--quiet", "--now", "--global")]
    if not args:
        return 1
    verb, units = args[0], args[1:]
    active, enabled = lines("active"), lines("enabled")
    if verb == "is-active":
        return 0 if units and units[0] in active else 3
    if verb == "cat":
        return 0 if units and units[0] in lines("units") else 1
    if verb == "enable":
        put("enabled", enabled | set(units))
        if "--now" in sys.argv:
            put("active", active | set(units))
    elif verb == "start":
        put("active", active | set(units))
    elif verb == "stop":
        put("active", active - set(units))
    return 0


def main(name: str) -> int:
    with open(STATE / "calls", "a") as f:
        f.write(" ".join([name, *sys.argv[1:]]) + "\n")
    if name == "systemctl":
        return systemctl(sys.argv[1:])
    if name == "pgrep":
        return 0 if sys.argv[-1] in lines("running") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[0]).name))
