"""What a Quick Rescue leaves in the backup for later (SPEC §12; audit 1.11,
8.4; 1.x's skipped_system and "Put AI models back"): the big Quick skips
items in the home folder, and AI models in the system area (Ollama's), so the
rescue gets back to a working desktop fast. They come back with Restore my
files (Choose what comes back offers them under its Quick skips), and the
guard (core/partial.py) counts them as still on the backup until they do.
"""

from omabackups.tui.quick import QUICK

LATER = ("models", "games", "flatpak", "vms")      # Quick skips ids, in this order


def items() -> list:
    return [q for q in QUICK if q.id in LATER]


def label(item_id: str) -> str:
    return next((q.label for q in QUICK if q.id == item_id), item_id)


# In the system area only AI models wait (as 1.x): they're just
# big files. Flatpak, Docker, containers and VM data belong to services that
# start with the system, so they come back with it, whole.
SYSTEM_LATER = ("models",)


def system_paths() -> list[str]:
    """The system-area places (absolute), for the rescue's excludes."""
    return [p for q in items() if q.id in SYSTEM_LATER for p in q.system]


def home_rules(user: str) -> dict[str, list[str]]:
    """Each item's home rules, relative to the home folder (as Choose what
    comes back's leave-out list writes them: "/.ollama/models")."""
    out = {}
    for q in items():
        out[q.id] = [r.replace("/{u}", "") if r.startswith("/{u}/") else r.replace("{u}", user)
                     for r in q.home]
    return out


def brought(only: list[str] | None, leave_out: list[str], leave_out_system: list[str]) -> list[str]:
    """The items a finished Restore my files run brought back: everything
    was asked for, and none of the item's places was left in the backup."""
    if only is not None:
        return []
    left = set(leave_out) | set(leave_out_system)
    rules = home_rules("")
    return [q.id for q in items()
            if not any(r in left for r in rules[q.id] + (list(q.system) if q.id in SYSTEM_LATER else []))]
