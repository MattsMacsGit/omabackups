"""System tweaks (1.x's idea, rebuilt): files in the system's own places that
no package owns and Omarchy didn't make, so you set them up yourself.
A service and the command it runs are one tweak.
"""

import os
import re
import subprocess
from pathlib import Path

from omabackups.audit import omarchy
from omabackups.audit.model import item

PLACES = (
    ("/usr/local/bin", "command"), ("/usr/local/sbin", "command"),
    ("/etc/systemd/system", "unit"), ("/etc/systemd/user", "unit"),
    ("/etc/systemd", "systemd-conf"),
    ("/etc/udev/rules.d", "udev"), ("/etc/modprobe.d", "modprobe"),
    ("/etc/modules-load.d", "modules"), ("/etc/sysctl.d", "sysctl"),
    ("/etc/tmpfiles.d", "tmpfiles"), ("/etc/profile.d", "profile"),
    ("/etc/X11/xorg.conf.d", "xorg"), ("/etc/NetworkManager/conf.d", "nm"),
    ("/etc/NetworkManager/dispatcher.d", "nm-dispatcher"), ("/etc/polkit-1/rules.d", "polkit"),
)
UNITS = (".service", ".timer", ".path", ".socket", ".mount", ".automount", ".target")
WHAT = {"command": "Command", "udev": "Device rule", "modprobe": "Driver option",
        "modules": "Driver loaded at start-up", "sysctl": "Kernel setting",
        "tmpfiles": "Folder or file made at start-up", "profile": "Login shell setting",
        "xorg": "X11 setting", "nm": "Network setting", "nm-dispatcher": "Runs when the network changes",
        "polkit": "Permission rule"}
SYSTEMD_CONF = {"logind.conf.d": "Lid, power button and idle", "sleep.conf.d": "Sleep and hibernate",
                "system.conf.d": "Start-up and shutdown", "journald.conf.d": "System log",
                "resolved.conf.d": "Name lookups (DNS)", "timesyncd.conf.d": "Clock",
                "coredump.conf.d": "Crash dumps", "zram-generator.conf.d": "Compressed swap"}
RESTART = {"systemd-conf", "modprobe", "modules", "udev", "sysctl", "xorg"}
# OmaBackups puts its own back when it's set up again (2.0 and 1.x names).
OWN = re.compile(r"^(omabackups|oma-backups|omarchy-backups|omarchy-tm|oma-migrate|oma-gate)|"
                 r"^(50|99)-omabackups|^99-oma-backups")
KEEP = "you set this up yourself; a fresh install won't have it"


def _files(folder: Path) -> list[Path]:
    try:
        return sorted(f for f in folder.iterdir() if f.is_file() or f.is_symlink())
    except OSError:
        return []


def candidates() -> list[tuple[Path, str]]:
    out = []
    for place, kind in PLACES:
        base = Path(place)
        if kind == "systemd-conf":
            subs = [s for s in (sorted(base.iterdir()) if base.is_dir() else [])
                    if s.is_dir() and s.name.endswith(".conf.d")]
            out += [(f, kind) for s in subs for f in _files(s) if f.name.endswith(".conf")]
        elif kind == "unit":
            out += [(f, "unit") for f in _files(base) if f.name.endswith(UNITS) and not f.is_symlink()]
            subs = [s for s in (sorted(base.iterdir()) if base.is_dir() else [])
                    if s.is_dir() and s.name.endswith(tuple(u + ".d" for u in UNITS))]
            out += [(f, "dropin") for s in subs for f in _files(s)
                    if f.name.endswith(".conf") and not f.is_symlink()]
        else:
            out += [(f, kind) for f in _files(base)]
    return [(f, k) for f, k in out if not OWN.search(f.name)]


def owned(paths: list[Path]) -> set[str]:
    found = set()
    for n in range(0, len(paths), 200):
        chunk = [str(p) for p in paths[n:n + 200]]
        try:
            done = subprocess.run(["pacman", "-Qo", *chunk], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return {str(p) for p in paths}     # can't tell: offer nothing rather than everything
        found |= {m.group(1) for m in re.finditer(r"^(/.+) is owned by ", done.stdout, re.M)}
    return found


def first_comment(p: Path) -> str:
    try:
        if p.stat().st_size > 256 * 1024:
            return ""
        for line in p.read_text(errors="replace").splitlines()[:30]:
            t = line.strip()
            if t.startswith("#!") or not t:
                continue
            if t.startswith(("#", "//", ";")):
                t = t.lstrip("#/; ").strip()
                if len(t) > 8:
                    return t[:140]
            elif not t.startswith("["):
                break
    except OSError:
        pass
    return ""


def _unit(p: Path) -> tuple[str, list[str]]:
    desc, execs = "", []
    try:
        for line in p.read_text(errors="replace").splitlines():
            t = line.strip()
            if t.startswith("Description=") and not desc:
                desc = t.split("=", 1)[1].strip()
            elif t.startswith("Exec") and "=" in t:
                execs += [w.lstrip("-@:+!") for w in t.split("=", 1)[1].split() if w.lstrip("-@:+!").startswith("/")]
    except OSError:
        pass
    return desc, execs


def tweaks() -> list[dict]:
    keep = []
    for f, k in candidates():
        if f.is_symlink() and os.path.realpath(f).startswith(("/usr/lib/", "/usr/bin/", "/usr/share/")):
            continue
        keep.append((f, k))
    mine = owned([f for f, _ in keep])
    keep = [(f, k) for f, k in keep if str(f) not in mine and not omarchy.made_by_omarchy(f)]
    by_path, used, items = {str(f): f for f, _ in keep}, set(), []
    for f, k in keep:
        if k != "unit":
            continue
        desc, execs = _unit(f)
        group = [f] + [by_path[e] for e in execs if e in by_path and e != str(f)]
        used |= {str(x) for x in group}
        user = f.parent.name == "user"
        what = desc or first_comment(f) or f"A {'user' if user else 'system'} service you added"
        if len(group) > 1:
            what += " (runs " + ", ".join(str(x) for x in group[1:]) + ")"
        items.append(item(f"tweak:{f}", "tweaks", f"{f.stem} ({f.suffix[1:]})", "file", [f.name],
                          [str(x) for x in group], "keep", 30, what, KEEP,
                          "you'd have to set it up again by hand", needs_admin=True,
                          units=[{"name": f.name, "user": user}]))
    for f, k in keep:
        if str(f) in used:
            continue
        if k == "dropin":
            unit = f.parent.name[:-2]
            name, what = f"Change to {unit}", first_comment(f) or f"Your change to how {unit} runs"
        elif k == "systemd-conf":
            name = f"{SYSTEMD_CONF.get(f.parent.name, f.parent.name[:-7])}: {f.stem}"
            what = first_comment(f) or f"Your systemd setting {f.parent.name}/{f.name}"
        else:
            name, what = f"{WHAT.get(k, 'File')}: {f.name}", first_comment(f) or str(f)
        polkit = k == "polkit"
        items.append(item(f"tweak:{f}", "tweaks", name, "file", [f.name], [str(f)],
                          "you" if polkit else "keep", 20 if k == "command" else 22, what,
                          "it changes what may run as admin; bring it back if you still use it"
                          if polkit else KEEP, "you'd have to set it up again by hand",
                          needs_admin=True, restart=k in RESTART))
    return items
