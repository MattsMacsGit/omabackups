"""Bring settings and System tweaks back, as 1.x's Migrate did (D41), as root.

The order is 1.x's (backup.sh cmd_migrate_apply), proven on a fresh install:
  1. Fetch everything from the backup while every service still runs (the
     network or Tailscale may be the way to the backup): settings a service
     uses go to a holding folder, the rest straight into place. Also fetched:
     the old system's list of switched-on services, and its theme.
  2. Let go of the backup (the caller locks it).
  3. Each service in turn: stop it, put its settings in, switch it on if the
     old system had it on, start it. The network managers are never
     stopped: they reload.
  4. Your own units in /etc/systemd switched on; the old user name fixed in
     the settings that came over; then a check that each thing is really back.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from omabackups.migrate import rename, services

THEME_NAME = ".local/state/omarchy/current/theme.name"
BACKGROUND = ".local/state/omarchy/current/background"


def systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--no-ask-password", *args], capture_output=True, text=True)


def active(unit: str) -> bool:
    return systemctl("is-active", "--quiet", unit).returncode == 0


class Fetched:
    """Step 1's results: what's waiting in the holding folder, and what was read."""

    def __init__(self, stage: Path):
        self.stage, self.held, self.on, self.theme, self.problems = stage, {}, set(), {}, []


def fetch(get, home: Path, root: Path, stage: Path, from_user: str, home_items: list[str],
          system_items: list[str], theme: bool) -> Fetched:
    """Step 1. get(part, items, dest, owned) -> error text ("" when fine):
    rsync those paths of the restore point's part into dest (owned: the
    files belong to this user)."""
    out = Fetched(stage)
    plain, out.held = services.split(system_items)
    if home_items and (err := get(f"home/{from_user}", home_items, home, True)):
        out.problems.append({"what": "Some settings in your home folder didn't come back.", "details": err})
    if plain and (err := get("system", plain, root, False)):
        out.problems.append({"what": "Some System tweaks didn't come back.", "details": err})
    for svc, items in out.held.items():
        if err := get("system", items, stage / svc, False):
            out.problems.append({"what": f"The settings for {svc} didn't come back.", "details": err})
    # Which services the old system had on: its /etc/systemd/system (1.x).
    if out.held and not get("system", ["etc/systemd/system"], stage / "@old", False):
        out.on = services.enabled(stage / "@old/etc/systemd/system")
    if theme and not get(f"home/{from_user}", [THEME_NAME, BACKGROUND], stage / "@theme", False):
        name = stage / "@theme" / THEME_NAME
        link = stage / "@theme" / BACKGROUND
        out.theme = {"name": name.read_text().strip() if name.is_file() else "",
                     "background": os.readlink(link) if link.is_symlink() else ""}
    return out


def swap(fetched: Fetched, root: Path) -> tuple[list[dict], list[dict]]:
    """Step 3: each service's settings go in with it stopped; then it comes
    back as the old system had it. Returns (services, problems)."""
    report, problems = [], []
    for svc in sorted(fetched.held):
        unit, live = f"{svc}.service", svc in services.LIVE
        was_running = active(unit)
        if was_running and not live and systemctl("stop", unit).returncode != 0:
            problems.append({"what": f"{svc} couldn't be stopped to put its settings in.", "details": ""})
        done = subprocess.run(["rsync", "-a", "--numeric-ids", f"{fetched.stage / svc}/", f"{root}/"],
                              capture_output=True, text=True)
        if done.returncode != 0:
            problems.append({"what": f"The settings for {svc} couldn't be put in place.",
                             "details": done.stderr.strip()[-2000:]})
        if live:
            if svc == "NetworkManager" and was_running:
                systemctl("reload", unit)
            report.append({"service": svc, "on": True, "running": active(unit)})
            continue
        turn_on = services.was_on(svc, fetched.on) and systemctl("cat", unit).returncode == 0
        if turn_on:
            done = systemctl("enable", unit)
            if done.returncode != 0:
                problems.append({"what": f"{svc} couldn't be switched on.", "details": done.stderr.strip()})
        if (was_running or turn_on) and systemctl("start", unit).returncode != 0:
            problems.append({"what": f"{svc} couldn't be started.", "details": systemctl("status", unit).stdout[-2000:]})
        report.append({"service": svc, "on": turn_on, "running": active(unit),
                       "was_on": services.was_on(svc, fetched.on)})
    return report, problems


def units(wanted: list) -> list[dict]:
    """Your own units (System tweaks), switched on as they were on the old computer."""
    problems = []
    if not wanted:
        return problems
    systemctl("daemon-reload")
    for unit in wanted if isinstance(wanted, list) else []:
        name = str(unit.get("name", "")) if isinstance(unit, dict) else ""
        if not name or "/" in name or not name.endswith((".service", ".timer", ".path", ".socket")):
            continue
        # A user unit: switched on for every user, as it was in /etc/systemd/user.
        done = systemctl("--global", "enable", name) if unit.get("user") else systemctl("enable", "--now", name)
        if done.returncode != 0:
            problems.append({"what": f"{name} couldn't be switched on.", "details": done.stderr.strip()})
    return problems


def missing(home: Path, root: Path, home_items: list[str], system_items: list[str]) -> list[dict]:
    """Step 4's check: every setting asked for is really here now (1.x)."""
    gone = [f"~/{i}" for i in home_items if not os.path.lexists(home / i)]
    gone += [f"/{i}" for i in system_items if not os.path.lexists(root / i)]
    return [{"what": f"{g} isn't back (it may not be in that restore point).", "details": ""} for g in gone]


def run(get, home: Path, root: Path, from_user: str, user: str, home_items: list[str],
        system_items: list[str], unit_list: list, theme: bool, let_go) -> dict:
    """The whole of it. let_go(): step 2, called once everything is fetched."""
    base = root / "var/tmp"
    base.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="omabackups-migrate.", dir=base))
    try:
        try:
            fetched = fetch(get, home, root, stage, from_user, home_items, system_items, theme)
        finally:
            let_go()
        report, problems = swap(fetched, root)
        problems = fetched.problems + problems + units(unit_list)
        renamed = rename.fix(home, home_items, f"/home/{from_user}") if from_user != user else []
        problems += missing(home, root, home_items, system_items)
        return {"services": report, "theme": fetched.theme, "renamed": renamed, "problems": problems,
                "home": len(home_items), "system": len(system_items)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)
