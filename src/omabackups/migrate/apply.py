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

from omabackups.migrate import merge, rename, services

# Where Omarchy keeps the theme in use: since June 2026 in ~/.local/state,
# before that in ~/.config (D42: any release). Read from whichever is there.
THEME_PLACES = (".local/state/omarchy/current", ".config/omarchy/current")


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
    if theme:
        out.theme = _theme(get, from_user, stage / "@theme")
    return out


def _theme(get, from_user: str, where: Path) -> dict:
    """The old theme's name and background, from either layout."""
    get(f"home/{from_user}", [f"{p}/{n}" for p in THEME_PLACES for n in ("theme.name", "theme", "background")],
        where, False)            # some aren't there: that's expected
    for place in THEME_PLACES:
        name_file, theme, link = where / place / "theme.name", where / place / "theme", where / place / "background"
        name = name_file.read_text().strip() if name_file.is_file() else \
            os.path.basename(os.readlink(theme).rstrip("/")) if theme.is_symlink() else ""
        if name:
            return {"name": name, "background": os.readlink(link) if link.is_symlink() else ""}
    return {}


def merged(get, home: Path, root: Path, stage: Path, from_user: str, items: list[dict]) -> tuple[list, list]:
    """Keybindings, bar & theme (D43): each file merged onto this release's.
    Returns (files merged, problems)."""
    done, problems = [], []
    if not items:
        return done, problems
    get(f"home/{from_user}", [i["path"] for i in items], stage / "@merge/home", False)
    get("system", [i["stock"] for i in items], stage / "@merge/system", False)
    plugins = _plugins(home)
    keep = lambda wid: str(wid).startswith("omarchy.") or wid in plugins  # noqa: E731
    owner = home.stat()
    for i in items:
        old = stage / "@merge/home" / i["path"]
        if not old.is_file():
            continue
        stock_file = stage / "@merge/system" / i["stock"]
        stock = stock_file.read_text(errors="replace") if stock_file.is_file() else None
        here = home / i["path"]
        new_file = here if here.is_file() else root / i["stock"]
        new = new_file.read_text(errors="replace") if new_file.is_file() else ""
        mine = old.read_text(errors="replace")
        try:
            if i["kind"] == "json":
                text, unplaced = merge.shell(stock, mine, new or mine, keep), []
            else:
                text, unplaced = merge.lua(stock, mine, new)
        except ValueError as exc:
            problems.append({"what": f"~/{i['path']} couldn't be merged; yours is kept as "
                                     f"~/{i['path']}.from-old-system to look at.", "details": str(exc)})
            text, unplaced = None, []
        if text is None or not text.strip():
            _write(home / (i["path"] + ".from-old-system"), mine, owner)
            continue
        if here.is_file():
            _write(home / (i["path"] + ".omabackups-before"), here.read_text(errors="replace"), owner)
        _write(here, text, owner)
        done.append(i["path"])
        if unplaced:
            problems.append({"what": f"Some of your changes to ~/{i['path']} don't fit this Omarchy; "
                                     "they're listed here to add by hand if you still want them.",
                             "details": "\n".join(unplaced)})
    return done, problems


def _plugins(home: Path) -> set:
    import json
    ids = set()
    for manifest in (home / ".config/omarchy/plugins").glob("*/manifest.json"):
        try:
            ids.add(json.loads(manifest.read_text()).get("id"))
        except (OSError, ValueError):
            pass
    return ids


def _write(path: Path, text: str, owner) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".omabackups-tmp")
    tmp.write_text(text)
    os.chown(tmp, owner.st_uid, owner.st_gid)
    os.replace(tmp, path)


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
        system_items: list[str], unit_list: list, theme: bool, let_go, merges: list | None = None) -> dict:
    """The whole of it. let_go(): step 2, called once everything is fetched."""
    base = root / "var/tmp"
    base.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="omabackups-migrate.", dir=base))
    try:
        try:
            fetched = fetch(get, home, root, stage, from_user, home_items, system_items, theme)
            desk, desk_problems = merged(get, home, root, stage, from_user, merges or [])
        finally:
            let_go()
        report, problems = swap(fetched, root)
        problems = fetched.problems + desk_problems + problems + units(unit_list)
        later: list[str] = []
        renamed = rename.fix(home, home_items + desk, f"/home/{from_user}", later) if from_user != user else []
        rename.save_later(home, f"/home/{from_user}", later)
        problems += missing(home, root, home_items, system_items)
        return {"services": report, "theme": fetched.theme, "renamed": renamed, "later": later, "merged": desk,
                "problems": problems,
                "home": len(home_items), "system": len(system_items)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)
