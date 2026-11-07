"""Apps the user added (1.x's scanner, rebuilt): installed packages minus
what Omarchy installs, each with its settings folders; and Flatpaks.

Something one of your apps needs goes with that app (libfprint with fprintd);
something Omarchy needs comes back with Omarchy. Settings folders come from
the known list, else are guessed from the app's names (its command, its
menu entry, its package name) in the usual places.
"""

import re
import subprocess
from pathlib import Path

from omabackups.audit import omarchy
from omabackups.audit.model import item

LIBRARY = re.compile(r"^(lib.+|python-.+|perl-.+|ruby-.+|lua-.+|nodejs-.+|.+-headers|.+-docs?|"
                     r"ttf-.+|otf-.+|noto-.+)$")
SUFFIX = re.compile(r"-(bin|git|appimage|desktop|beta|nightly|stable|electron|wayland|vulkan|cuda|rocm)$")
OWN = {"omabackups"}      # OmaBackups brings itself back
PLACES = ("~/.config", "~/.local/share", "~/.local/state", "~", "~/.var/app", "/var/lib")


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


class Finder:
    """Matches app names against the folders where apps keep settings."""

    def __init__(self, home: Path, shared: set[str]):
        self.home, self.shared, self.index, self.claimed = home, {s.lower() for s in shared}, {}, set()
        for place in PLACES:
            folder = self.expand(place)
            try:
                entries = list(folder.iterdir())
            except OSError:
                continue
            for e in entries:
                name = e.name
                if place == "~":
                    if not name.startswith("."):
                        continue          # visible home folders are the user's files
                    name = name[1:]
                key = name.lower()
                if key not in self.shared and len(key) >= 3:
                    self.index.setdefault(key, []).append(e)

    def expand(self, p: str) -> Path:
        return self.home / p[2:] if p.startswith("~/") else self.home if p == "~" else Path(p)

    def tilde(self, p: Path) -> str:
        s = str(p)
        return "~" + s[len(str(self.home)):] if s.startswith(str(self.home)) else s

    def find(self, names: set[str]) -> list[Path]:
        hits = []
        for n in {n.lower() for n in names if n}:
            if len(n) < 3 or n in self.shared:
                continue
            for v in {n, n.replace(" ", ""), n.replace(" ", "-"), n.replace("-", ""), n.replace("_", "-")}:
                hits += [p for p in self.index.get(v, []) if p not in hits and p not in self.claimed]
        return hits

    def claim(self, paths) -> None:
        self.claimed.update(paths)


def _info(pkgs: list[str]) -> dict:
    out, current = {}, None
    for line in _run(["pacman", "-Qi", *pkgs]).splitlines() if pkgs else []:
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "Name":
            current = out.setdefault(value, {"desc": "", "required_by": []})
        elif current is not None and key == "Description":
            current["desc"] = value
        elif current is not None and key == "Required By":
            current["required_by"] = [] if value == "None" else value.split()
    return out


def _files(pkgs: list[str]) -> dict:
    out = {}
    for line in _run(["pacman", "-Ql", *pkgs]).splitlines() if pkgs else []:
        pkg, _, path = line.partition(" ")
        out.setdefault(pkg, []).append(path)
    return out


def _desktop_name(path: str) -> str | None:
    try:
        for line in Path(path).read_text(errors="replace").splitlines():
            if line.startswith("Name="):
                return line[5:].strip()
    except OSError:
        pass
    return None


def _names(pkg: str, files: list[str], pretty: str | None) -> set[str]:
    names = {pkg, SUFFIX.sub("", pkg), pretty or ""}
    for f in files:
        base = Path(f).name
        if f.startswith("/usr/share/applications/") and base.endswith(".desktop"):
            names |= {base[:-8], base[:-8].split(".")[-1]}
        elif f.startswith("/usr/bin/"):
            names.add(base)
    return names


def packages(home: Path, known: dict, finder: Finder) -> tuple[list[dict], dict]:
    stock = omarchy.stock_packages()
    explicit, foreign = _run(["pacman", "-Qqe"]).split(), set(_run(["pacman", "-Qqm"]).split())
    notes = {"installer": [], "needed_by_omarchy": [], "grouped_with": {}}
    cands = []
    for p in explicit:
        if p in stock or p in OWN:
            continue
        (notes["installer"] if omarchy.installer_package(p) else cands).append(p)
    info, files, cset = _info(cands), _files(cands), set(cands)

    parent = {}
    for p in cands:
        req = info.get(p, {}).get("required_by", [])
        owners = sorted(r for r in req if r in cset and r != p)
        if owners:
            parent[p] = owners[0]
        elif any(r in stock for r in req):
            parent[p] = ""

    def top(p: str) -> str:
        seen = set()
        while parent.get(p) and p not in seen:
            seen.add(p)
            p = parent[p]
        return p

    groups = {}
    for p in cands:
        if parent.get(p) == "":
            notes["needed_by_omarchy"].append(p)
        else:
            groups.setdefault(top(p), []).append(p)

    apps, items = known.get("apps", {}), []
    weight = lambda head: max((float(apps[m].get("weight", 0)) for m in groups[head] if m in apps),  # noqa: E731
                              default=0.0)
    for head in sorted(groups, key=weight, reverse=True):
        members = [head] + sorted(m for m in groups[head] if m != head)
        if len(members) > 1:
            notes["grouped_with"][head] = members[1:]
        k = next((apps[m] for m in members if m in apps), None)
        gui = [f for m in members for f in files.get(m, []) if f.endswith(".desktop")]
        pretty = (k or {}).get("name") or (_desktop_name(gui[0]) if gui else None)
        paths = [finder.expand(x) for x in (k or {}).get("paths", []) if finder.expand(x).exists()]
        for m in members:
            paths += [p for p in finder.find(_names(m, files.get(m, []), pretty if m == head else None))
                      if p not in paths]
        paths = [p for p in paths if p not in finder.claimed]
        finder.claim(paths)
        library = all(LIBRARY.match(m) for m in members) and not gui
        if k:
            suggest, why, w = k["suggest"], k.get("why", ""), float(k.get("weight", 30))
        elif library:
            suggest, why, w = "leave", "a building block: anything that needs it installs it again", 5
        elif paths:
            suggest, why, w = ("keep" if gui else "you"), "your settings come back with it", 35 if gui else 18
        else:
            suggest, why, w = "you", "nothing to bring back with it", 20 if gui else 10
        source = "the AUR" if any(m in foreign for m in members) else "Arch's packages"
        items.append(item(
            f"app:{head}", "apps", pretty or head, "package", members, [finder.tilde(p) for p in paths],
            suggest, w, info.get(head, {}).get("desc", ""), why,
            f"quick to install again (from {source})" + (", with its settings" if paths else "")))
    return items, notes


def flatpaks(user: str, known: dict, finder: Finder) -> list[dict]:
    items = []
    listing = _run(["runuser", "-u", user, "--", "flatpak", "list", "--app",
                    "--columns=application,name"]) if user else ""
    for line in listing.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        app_id, name = parts[0], parts[1]
        k = known.get("apps", {}).get(app_id) or {}
        data = finder.expand(f"~/.var/app/{app_id}")
        paths = [data] if data.exists() else []
        finder.claim(paths)
        items.append(item(f"flatpak:{app_id}", "apps", k.get("name", name), "flatpak", [app_id],
                          [finder.tilde(p) for p in paths], k.get("suggest", "keep" if paths else "you"),
                          float(k.get("weight", 30)), "A Flatpak app.",
                          k.get("why", "your settings come back with it" if paths else ""),
                          "quick to install again from Flathub"))
    return items
