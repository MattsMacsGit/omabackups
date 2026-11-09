"""`omabackups migrate`: Migrate from another system (6.1 F), in a terminal
window the panel opens; also Run Migrate again (D38), any time after.

1. Connect to your backup (a server: its address, your login there, the
   server's sudo for OmaBackups' own part, then your backup's password).
2. Pick the restore point.  3. Choose what comes over.
4. Migrate: apps, then settings and System tweaks (1.x's order, D41), then
your files if now. The report says what came over and what needs a look.
5. Omarchy restarts to apply it all (D41): you land on your own desktop.
"""

import os
import sys
import time
from pathlib import Path

from omabackups.core import flow, paths, rootjob, state
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    p = sub.add_parser("migrate", help="Migrate from another system (or Run Migrate again)")
    p.add_argument("address", nargs="?", help="the backup server's address")
    p.add_argument("--login", help="your user name on the server")
    p.add_argument("--preview", action="store_true",
                   help="show the screens with this computer's own list; nothing changes")
    p.set_defaults(run=run)


def when(name: str) -> str:
    from omabackups.backup.thinning import when as parse
    d = parse(name)
    return f"{d:%a %-d %b %Y, %-I:%M %p}" if d else name


def _connect(args) -> dict:
    """Step 1, on a computer that doesn't back up anywhere yet."""
    from omabackups.setup import menu, server
    menu.title("Migrate from another system",
               "Connect to the backup of your old computer. Passwords: this computer's\n"
               "(a pop-up), your password on the server twice (to log in, then for sudo),\n"
               "then your backup's own password.")
    address = args.address or menu.ask("The backup server's address", placeholder="for example 192.168.1.20")
    login = args.login or menu.ask("Your user name on the server", os.environ.get("USER", ""))
    if not address or not login:
        raise OmaError("The server's address and your user name on it are both needed.", code="cancelled")
    pub = server.link()
    session = server.Login(address, login)
    try:
        menu.title("Logging in to your backup server", "SSH asks for your password on the server, to log you in.")
        if session.run("true").returncode == 255:
            raise OmaError("Couldn't log in to your backup server.",
                           "Check the address, your user name and its password, then try again.",
                           code="setup-server")
        server.install(session, "-", pub)    # this computer's key, next to the backup
    finally:
        session.close()
    menu.title("Your backup's password", "The one you chose when you set up backups on the old computer.")
    request = {"address": address, "host_keys": session.host_keys(), "password": menu.secret("Your backup's password")}
    answer = rootjob.run("migrate-join", request)
    if "choose" in answer:
        found = answer["choose"]
        labels = [f"Made {time.strftime('%a %-d %b %Y', time.localtime(b.get('created') or 0))}"
                  f"  ·  {b['id'][:12]}" for b in found]
        request["backup"] = found[menu.choose("That password opens more than one backup. Which one?", labels)]["id"]
        answer = rootjob.run("migrate-join", request)
    return answer


def _pick_point(points: list[str]) -> str:
    from omabackups.setup import menu
    newest = sorted(points, reverse=True)
    if not newest:
        raise OmaError("That backup has no restore points yet.",
                       "Back up the old computer first, then Migrate.", code="no-points")
    menu.title("Which restore point should Migrate start from?", "The newest is usually the one.")
    labels = [f"{when(p)}  ·  line {p[:3]}" for p in newest]
    return newest[menu.choose("Restore points", labels)]


def _close_first(job: dict) -> None:
    """Apps that rewrite their settings when they quit are closed first (1.x)."""
    from omabackups.migrate import running
    from omabackups.setup import menu
    apps = running.holders(job["home"])
    user = os.environ.get("USER", "")
    while open_now := running.still_open(apps, user):
        menu.title(f"Close {', '.join(open_now)} first",
                   "It rewrites its settings when it closes, so it would undo what Migrate\n"
                   "brings back. Close it (all its windows), then press Enter.")
        menu.ask("Press Enter once it's closed")


def _apply(point: str, changes: dict, chosen: dict, say) -> dict:
    from omabackups.migrate import apps, plan
    job = plan.jobs(changes, set(chosen["picked"]))
    from_user = changes.get("user") or ""
    _close_first(job)
    problems = apps.install(job, say)
    say("Bringing back your settings and System tweaks...")
    done = rootjob.run("migrate-settings", {"point": point, "from_user": from_user, "home": job["home"],
                                            "system": job["system"], "units": job["units"]})
    problems += [{"name": "", **p} for p in done.get("problems", [])]
    problems += _relink_tools(say)
    for svc in done.get("services", []):
        if svc.get("was_on") and not svc.get("running"):
            problems.append({"name": svc["service"], "what": "is back but isn't running."})
    files_now = bool(job["files"]) and chosen["files_now"]
    if files_now:
        say("Bringing back your files (the panel shows how far)...")
        rootjob.run("restore-files-start", {"point": point, "from_user": from_user, "only": job["files"]})
    return {"job": job, "problems": problems, "files_now": files_now, "skipped": job["skipped"],
            "services": done.get("services", []), "renamed": done.get("renamed", [])}


def _relink_tools(say) -> list[dict]:
    """GitHub's login helper for git names gh's path, which changes with each
    gh version and user name: set it again (1.x test, 5 Nov)."""
    import shutil
    import subprocess
    if not shutil.which("gh") or not (Path.home() / ".config/gh/hosts.yml").exists():
        return []
    done = subprocess.run(["gh", "auth", "setup-git"], capture_output=True, text=True)
    if done.returncode != 0:
        return [{"name": "GitHub", "what": "git's GitHub login couldn't be set up: run gh auth setup-git after the restart."}]
    say("GitHub login linked for git.")
    return []


def preview(events: Events) -> int:
    """The Migrate screens, read only, with this computer's own list (the one
    its latest backup made): to see what it looks like and what it would do."""
    import json
    from omabackups.migrate import plan
    from omabackups.setup import menu
    from omabackups.tui import migrate_pick
    try:
        changes = json.loads((paths.system_state_dir() / "changes.json").read_text())
    except (OSError, ValueError):
        raise OmaError("There's no list of your changes on this computer yet.",
                       "Back up once (Back up now), then try the preview again.", code="no-changes") from None
    made = time.strftime("%a %-d %b %Y, %-I:%M %p", time.localtime(changes.get("made") or time.time()))
    chosen = migrate_pick.run(changes, made, preview=True)
    if chosen is None:
        events.result({"preview": True}, "Preview closed. Nothing was changed.")
        return 0
    job = plan.jobs(changes, set(chosen["picked"]))
    items = {i["id"]: i for i in changes.get("items", [])}
    picked = [items[i] for i in chosen["picked"] if i in items]
    menu.title("What Migrate would do (preview: nothing was changed)", plan.summary(job))
    groups = (("Install these apps", [i["name"] for i in picked if i["group"] == "apps"]),
              ("Bring back these settings", [i["name"] for i in picked if i["group"] in ("settings", "desktop", "backgrounds")]),
              ("Put back these System tweaks", [i["name"] for i in picked if i["group"] == "tweaks"]),
              ("Your files" + (", now" if chosen["files_now"] else ", later (Restore my files)"),
               [i["name"] for i in picked if i["group"] == "files"]))
    for label, values in groups:
        if values:
            menu.say(f"  {label}:")
            for v in values:
                menu.say(f"    {v}")
    for v in job["skipped"]:
        menu.say(f"  Needs a look: {v}")
    events.result({"preview": True, "picked": chosen["picked"]}, "Preview only: nothing was changed.")
    try:
        menu.ask("Press Enter to close this window")
    except OmaError:
        pass
    return 0


def run(args, events: Events) -> int:
    if args.preview and os.isatty(0) and os.isatty(1):
        return preview(events)
    if not (os.isatty(0) and os.isatty(1)):
        raise OmaError("Migrate needs a terminal window.",
                       "Start it from the panel (it opens one), or run omabackups migrate in a terminal.",
                       code="no-terminal")
    from omabackups.setup import menu
    from omabackups.tui import migrate_pick
    try:
        import json
        server = json.loads(paths.server_file().read_text())
    except (OSError, ValueError):
        server = {}
    again = bool(server) and not server.get("migrating")
    if server.get("migrating") or again:
        listing = rootjob.run("migrate-points", {})
    else:
        listing = _connect(args)
    point = _pick_point(listing["points"])
    info = rootjob.run("migrate-info", {"point": point})
    changes = info.get("changes")
    if not changes:
        raise OmaError("That restore point has no list of your changes to Omarchy.",
                       "Pick a newer restore point: every backup makes one.", code="no-changes")
    chosen = migrate_pick.run(changes, when(point))
    if chosen is None:
        events.result({"migrated": False}, "Nothing was brought over.")
        return 0
    menu.title("Migrating", "Apps first, then settings. Some apps ask for this computer's password.")
    result = _apply(point, changes, chosen, lambda text: menu.say(f"  {text}"))
    job = result["job"]
    files_left = bool(job["files"]) and not result["files_now"]
    if not again:
        state.write(flow.MIGRATE, {"done": True, "files_restored": not files_left, "point": point,
                                   "from_user": changes.get("user") or "", "files": job["files"],
                                   "restart": job["restart"], "at": int(time.time())})
    lines = [f"Brought over: {_said(job)}."]
    for svc in result["services"]:
        if svc.get("running"):
            lines.append(f"  {svc['service']}: back on, running.")
    if result["renamed"]:
        lines.append(f"  Your old user name was changed to this one in {len(result['renamed'])} settings files.")
    for p in result["problems"] + [{"name": s, "what": ""} for s in result["skipped"]]:
        lines.append(f"  Needs a look: {p['name']} {p['what']}".rstrip())
    if files_left:
        lines.append("Your files: Restore my files on the panel brings them back while you work.")
    lines.append("After the restart: Back up now on the panel. This computer then takes the backup over."
                 if not again else "")
    events.result({"migrated": True, "point": point, "problems": result["problems"]},
                  "\n".join(x for x in lines if x))
    _finish(result["files_now"])
    return 0


def _finish(files_now: bool) -> None:
    """Wait for the files if they're coming now, then restart (D41)."""
    from omabackups.migrate import finish
    say = lambda text: menu_say(text)  # noqa: E731
    if files_now:
        state = finish.wait_for_files(say)
        if state.get("error"):
            say("Your files stopped coming back: " + state["error"].get("what", "") +
                " Restore my files on the panel carries on after the restart.")
    import subprocess
    finish.restart(say, lambda: subprocess.run(["systemctl", "reboot"]))


def menu_say(text: str) -> None:
    from omabackups.setup import menu
    menu.say(text)


def _said(job: dict) -> str:
    from omabackups.migrate import plan
    return plan.summary(job)
