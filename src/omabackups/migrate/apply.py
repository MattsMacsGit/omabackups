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

Everything done inside the home folder (merging, keeping copies aside,
fixing the user name, checking) runs as the user (D59: core/asuser.py,
migrate/home.py). What only root may read is fetched into `stage`; what the
user's steps read is fetched, theirs, into `ustage`.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from omabackups.core import asuser
from omabackups.migrate import rename, services
from omabackups.migrate.home import THEME_PLACES


def systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--no-ask-password", *args], capture_output=True, text=True)


def active(unit: str) -> bool:
    return systemctl("is-active", "--quiet", unit).returncode == 0


class Fetched:
    """Step 1's results: what's waiting in the holding folder, and what was read."""

    def __init__(self, stage: Path):
        self.stage, self.held, self.on, self.theme, self.problems = stage, {}, set(), {}, []


def fetch(get, home: Path, root: Path, stage: Path, from_user: str, home_items: list[str],
          system_items: list[str], theme: bool, ustage: Path | None = None,
          user: str | None = None) -> Fetched:
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
        out.theme = _theme(get, from_user, (ustage or stage) / "@theme", user)
    return out


def _theme(get, from_user: str, where: Path, user: str | None = None) -> dict:
    """The old theme's name and background, from either layout (read as the user)."""
    get(f"home/{from_user}", [f"{p}/{n}" for p in THEME_PLACES for n in ("theme.name", "theme", "background")],
        where, True)             # some aren't there: that's expected
    return asuser.run(user, "theme", {"where": str(where)})


def merged(get, home: Path, root: Path, stage: Path, from_user: str, items: list[dict],
           user: str | None = None) -> tuple[list, list]:
    """Keybindings, bar & theme (D43): each file merged onto this release's,
    by the user's own step (stage: the user's holding folder).
    Returns (files merged, problems)."""
    if not items:
        return [], []
    get(f"home/{from_user}", [i["path"] for i in items], stage / "@merge/home", True)
    get("system", [i["stock"] for i in items], stage / "@merge/system", True)
    done = asuser.run(user, "merge", {"home": str(home), "root": str(root),
                                      "stage": str(stage / "@merge"), "items": items})
    return done["done"], done["problems"]


def keep_first(listing: str, dest: Path, keep: Path) -> None:
    """D45: from a dry run's listing, the files here that the fetch will
    replace are copied to keep (same paths) before it runs."""
    for line in listing.splitlines():
        flags, name = line[:11], line[12:].partition(" ")[2]
        if len(flags) < 2 or flags[0] != ">" or flags[1] not in "fL" or "+++++" in flags or not name:
            continue
        here = dest / name
        if not os.path.lexists(here):
            continue
        target = keep / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(here, target, follow_symlinks=False)


def kept(home: Path, keep_home: Path, keep_root: Path, user: str | None = None) -> list[str]:
    """D45: where what Migrate replaced was kept (only if something was).
    The home copy was made by the user's own step, so it's theirs."""
    out = []
    if asuser.run(user, "kept", {"keep": str(keep_home)}):
        out.append(str(keep_home))
    if keep_root.is_dir() and any(keep_root.iterdir()):
        os.chmod(keep_root.parent, 0o700)
        out.append(str(keep_root))
    elif keep_root.is_dir():
        shutil.rmtree(keep_root, ignore_errors=True)
    return out


def swap(fetched: Fetched, root: Path, keep: Path | None = None) -> tuple[list[dict], list[dict]]:
    """Step 3: each service's settings go in with it stopped; then it comes
    back as the old system had it. Returns (services, problems)."""
    report, problems = [], []
    for svc in sorted(fetched.held):
        unit, live = f"{svc}.service", svc in services.LIVE
        was_running = active(unit)
        if was_running and not live and systemctl("stop", unit).returncode != 0:
            problems.append({"what": f"{svc} couldn't be stopped to put its settings in.", "details": ""})
        kept_ = ["--backup", f"--backup-dir={keep}"] if keep else []
        done = subprocess.run(["rsync", "-a", "--numeric-ids", *kept_, f"{fetched.stage / svc}/", f"{root}/"],
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


def crontab(root: Path, home: Path, from_user: str, user: str) -> list[dict]:
    """D46: a crontab is filed under the user name: the old one becomes this
    user's (cron ignores a file another user owns)."""
    old, new = root / "var/spool/cron" / from_user, root / "var/spool/cron" / user
    if from_user == user or not old.is_file():
        return []
    if new.exists():
        return [{"what": f"Your old scheduled jobs are in {old}: this user has its own already, "
                         "so they weren't put in its place. Copy what you need with crontab -e.",
                 "details": ""}]
    owner = home.stat()
    os.chown(old, owner.st_uid, owner.st_gid)
    os.chmod(old, 0o600)
    os.replace(old, new)
    return []


def missing(home: Path, root: Path, home_items: list[str], system_items: list[str],
            user: str | None = None) -> list[dict]:
    """Step 4's check: every setting asked for is really here now (1.x)."""
    gone = asuser.run(user, "missing", {"home": str(home), "items": home_items}) if home_items else []
    gone += [f"/{i}" for i in system_items if not os.path.lexists(root / i)]
    return [{"what": f"{g} isn't back (it may not be in that restore point).", "details": ""} for g in gone]


def run(get, home: Path, root: Path, from_user: str, user: str, home_items: list[str],
        system_items: list[str], unit_list: list, theme: bool, let_go, merges: list | None = None,
        keep: Path | None = None) -> dict:
    """The whole of it. let_go(): step 2, called once everything is fetched."""
    base = root / "var/tmp"
    base.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="omabackups-migrate.", dir=base))
    ustage = Path(tempfile.mkdtemp(prefix="omabackups-migrate-home.", dir=base))
    asuser.give(ustage, user)
    try:
        try:
            fetched = fetch(get, home, root, stage, from_user, home_items, system_items, theme, ustage, user)
            desk, desk_problems = merged(get, home, root, ustage, from_user, merges or [], user)
        finally:
            let_go()
        report, problems = swap(fetched, root, keep)
        problems += crontab(root, home, from_user, user)
        problems = fetched.problems + desk_problems + problems + units(unit_list)
        renamed, later = [], []
        if from_user != user:       # D44: names too (an app's folders named after the old home)
            fixed = asuser.run(user, "rename", {"home": str(home), "items": home_items + desk,
                                                "old_home": f"/home/{from_user}"})
            renamed, later = fixed["renamed"], fixed["later"]
        rename.save_later(home, f"/home/{from_user}", later)
        renamed_cron = [f"var/spool/cron/{user}" if i == f"var/spool/cron/{from_user}" else i
                        for i in system_items]
        problems += missing(home, root, home_items, renamed_cron, user)
        return {"services": report, "theme": fetched.theme, "renamed": renamed, "later": later, "merged": desk,
                "problems": problems,
                "home": len(home_items), "system": len(system_items)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(ustage, ignore_errors=True)     # fd-based: never follows the user's links
