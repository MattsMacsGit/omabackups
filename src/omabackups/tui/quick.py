"""Quick skips (BUILD 7.2, agreed 7 Nov): the curated switches that replace the
raw System tree. Each covers known big things in several places at once
(1.x's quick skips, plus the big system-side ones). The rest of the system
is always backed up: the Rescue USB needs it.

Rules use the same spelling as the skip list's defaults, so a default
(Caches, Trash, Package cache) shows as already skipped. "{u}" is the user.
"""

import glob
import os
from dataclasses import dataclass

HOME_SHARE = "/{u}/.local/share"


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
          home=(HOME_SHARE + "/containers", HOME_SHARE + "/docker", HOME_SHARE + "/libvirt",
                HOME_SHARE + "/gnome-boxes", HOME_SHARE + "/bottles", "/{u}/.var/app/org.gnome.Boxes",
                "/{u}/.var/app/com.usebottles.bottles"),
          system=("/var/lib/docker", "/var/lib/containers", "/var/lib/libvirt/images")),
    Quick("models", "AI models", "Large downloads you can fetch again.",
          home=("/{u}/.lmstudio/models", "/{u}/.ollama/models", HOME_SHARE + "/nomic.ai",
                HOME_SHARE + "/Jan"),
          system=("/var/lib/ollama",)),
    Quick("games", "Game libraries", "Games you can install again (Steam).",
          home=("/{u}/.steam", HOME_SHARE + "/Steam")),
)


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
