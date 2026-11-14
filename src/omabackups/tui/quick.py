"""Quick skips (BUILD 7.2, agreed 7 Nov): the curated switches that replace the
raw System tree. Each covers known big things in several places at once
(1.x's quick skips, plus the big system-side ones). The rest of the system
is always backed up: the Rescue USB needs it.

Rules use the same spelling as the skip list's defaults, so a default
(Caches, Trash, Package cache) shows as already skipped. "{u}" is the user.
"""

import glob
import os
import re
from dataclasses import dataclass

HOME_SHARE = "/{u}/.local/share"
# Only the big part you can get again is skipped; a program's settings, logins
# and saves always come with your files (Steam opens logged in, Bottles keeps
# each bottle). Steam installed normally or as a Flatpak.
STEAM = tuple(f"**/Steam/steamapps/{x}" for x in ("common", "appmanifest_*.acf", "shadercache",
                                                   "downloading", "workshop"))
BOTTLES_PARTS = ("runners", "dxvk", "vkd3d", "nvapi", "latencyflex", "temp")


@dataclass(frozen=True)
class Quick:
    id: str
    label: str
    note: str
    home: tuple = ()
    system: tuple = ()


QUICK = (
    Quick("downloads", "Downloads", "Things you downloaded; often easy to get again.",
          home=("/{u}/Downloads",)),
    Quick("caches", "Caches", "Made again whenever they're needed.",
          home=(".cache", ".thumbnails", ".var/app/*/cache")),
    Quick("trash", "Trash", "Files you've already thrown away.",
          home=("**/.local/share/Trash", ".Trash", "lost+found")),
    Quick("pkgcache", "Package cache", "App installers already used; downloaded again when needed.",
          system=("/var/cache/pacman/pkg",)),
    Quick("flatpak", "Flatpak apps", "The apps themselves; their documents and settings still come back.",
          home=(HOME_SHARE + "/flatpak",), system=("/var/lib/flatpak",)),
    Quick("vms", "Virtual machines & containers", "May hold things you keep inside them.",
          home=(HOME_SHARE + "/containers", HOME_SHARE + "/docker", HOME_SHARE + "/libvirt/images",
                HOME_SHARE + "/gnome-boxes/images", "/{u}/.var/app/org.gnome.Boxes/data/gnome-boxes/images",
                *(f"{HOME_SHARE}/bottles/{x}" for x in BOTTLES_PARTS),
                *(f"/{{u}}/.var/app/com.usebottles.bottles/data/bottles/{x}" for x in BOTTLES_PARTS)),
          system=("/var/lib/docker", "/var/lib/containers", "/var/lib/libvirt/images")),
    Quick("models", "AI models", "Large downloads you can fetch again.",
          home=("/{u}/.lmstudio/models", "/{u}/.ollama/models", HOME_SHARE + "/nomic.ai",
                HOME_SHARE + "/Jan"),
          system=("/var/lib/ollama",)),
    Quick("games", "Game libraries", "Games you can install again (Steam).", home=STEAM),
)

# What older switches skipped (whole folders) and what they skip now (14 Nov):
# a saved list is read the new way, so a switch that was on stays on.
NARROWED = {
    ".local/share/libvirt": (".local/share/libvirt/images",),
    ".local/share/gnome-boxes": (".local/share/gnome-boxes/images",),
    ".var/app/org.gnome.Boxes": (".var/app/org.gnome.Boxes/data/gnome-boxes/images",),
    ".local/share/bottles": tuple(f".local/share/bottles/{x}" for x in BOTTLES_PARTS),
    ".var/app/com.usebottles.bottles": tuple(f".var/app/com.usebottles.bottles/data/bottles/{x}"
                                             for x in BOTTLES_PARTS),
    ".steam": STEAM,
    ".local/share/Steam": STEAM,
}
_MINE = re.compile(r"^/([^/]+)/(.+)$")


def upgrade(patterns: list[str]) -> list[str]:
    """A saved skip list with an older switch's rules, read as it is now."""
    out = []
    for rule in patterns:
        m = _MINE.match(rule)
        now = NARROWED.get(m.group(2)) if m else None
        for new in (now if now is not None else (rule,)):
            new = new if now is None or new.startswith("**/") else f"/{m.group(1)}/{new}"
            if new not in out:
                out.append(new)
    return out


def rules(q: Quick, user: str) -> dict:
    return {"home": [r.replace("{u}", user) for r in q.home],
            "system": list(q.system)}


def places(q: Quick, user: str, roots: dict) -> list[str]:
    """The real folders a switch covers on this computer (for its size)."""
    found = []
    for part, items in rules(q, user).items():
        root = str(roots[part])
        for rule in items:
            if rule.startswith("/"):
                found += glob.glob(os.path.join(root, rule.lstrip("/")))
            else:   # any depth: look in the user's home
                found += glob.glob(os.path.join(root, user, "**", rule.removeprefix("**/")), recursive=True)
    # A match inside another match (a .cache inside a .cache) is counted once.
    tops = []
    for path in sorted(set(found)):
        if not any(path.startswith(top + "/") for top in tops):
            tops.append(path)
    return tops


def size(paths: list[str]) -> int:
    total = 0
    for top in paths:
        for root, _dirs, files in os.walk(top):
            for name in files:
                try:
                    total += os.lstat(os.path.join(root, name)).st_size
                except OSError:
                    pass
        if os.path.isfile(top):
            try:
                total += os.lstat(top).st_size
            except OSError:
                pass
    return total
