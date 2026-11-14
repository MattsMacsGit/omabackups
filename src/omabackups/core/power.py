"""On battery, and low? (SPEC §7; 1.x schedule.sh on_low_battery): under 20%
and discharging, automatic backups and the health check wait. A backup you
start yourself always runs."""

import os
from pathlib import Path

LOW = 20


def low_battery() -> bool:
    root = Path(os.environ.get("OMABACKUPS_SYSROOT") or "/") / "sys/class/power_supply"
    try:
        supplies = list(root.iterdir())
    except OSError:
        return False
    for supply in supplies:
        try:
            if (supply / "type").read_text().strip() != "Battery":
                continue
            if (supply / "status").read_text().strip() == "Discharging" and \
                    int((supply / "capacity").read_text().strip() or 100) < LOW:
                return True
        except (OSError, ValueError):
            continue
    return False
