"""Installing the ticked apps again (6.1 F step 4), in the Migrate terminal
window, as the user: through Omarchy's own commands (they try Omarchy's
mirrors and ask for the password themselves; yay never runs as root).

Each app is tried on its own, so one that can't be found doesn't stop the
rest; the report says which didn't come back and why.
"""

import shutil
import subprocess


def _ok(command: list[str]) -> tuple[bool, str]:
    try:
        done = subprocess.run(command, stderr=subprocess.PIPE, text=True)
    except OSError as exc:
        return False, str(exc)
    return done.returncode == 0, (done.stderr or "").strip()[-600:]


def in_repos(name: str) -> bool:
    return subprocess.run(["pacman", "-Si", "--", name], capture_output=True).returncode == 0


def installed(name: str) -> bool:
    return subprocess.run(["pacman", "-Q", "--", name], capture_output=True).returncode == 0


def install(job: dict, say) -> list[dict]:
    """Returns one entry per app that didn't come back: {name, what, details}."""
    problems = []
    wanted = [p for p in job["packages"] if not installed(p)]
    repo = [p for p in wanted if in_repos(p)]
    aur = [p for p in wanted if p not in repo]
    if repo:
        say(f"Installing {len(repo)} app{'s' if len(repo) != 1 else ''} from Arch's packages...")
        ok, details = _ok(["omarchy-pkg-add", *repo])
        if not ok:                                   # one by one, to find which
            for name in repo:
                ok, details = _ok(["omarchy-pkg-add", name])
                if not ok:
                    problems.append({"name": name, "what": "couldn't be installed", "details": details})
    for name in aur:
        say(f"Installing {name} from the AUR...")
        ok, details = _ok(["omarchy-pkg-aur-add", name])
        if not ok:
            problems.append({"name": name, "what": "couldn't be installed from the AUR", "details": details})
    if job["flatpaks"]:
        if shutil.which("flatpak"):
            for app in job["flatpaks"]:
                say(f"Installing {app} (Flatpak)...")
                ok, details = _ok(["flatpak", "install", "-y", "--noninteractive", "flathub", app])
                if not ok:
                    problems.append({"name": app, "what": "couldn't be installed (Flatpak)", "details": details})
        else:
            problems += [{"name": a, "what": "needs Flatpak, which isn't installed", "details": ""}
                         for a in job["flatpaks"]]
    for tool in job["tools"]:
        say(f"Installing {tool['name']} ({tool['command'].split(' ')[0]})...")
        ok, details = _ok(["bash", "-lc", tool["command"]])
        if not ok:
            problems.append({"name": tool["name"], "what": f"couldn't be installed ({tool['command']})",
                             "details": details})
    return problems
