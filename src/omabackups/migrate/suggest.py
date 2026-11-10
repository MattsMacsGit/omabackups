"""This version's suggestions, for a restore point made by an older one (D44).

The audit writes each row's suggestion (Keep / Up to you / Leave) into the
restore point at backup time. Migrate may read a point made long before, by
an older OmaBackups: its rows get the suggestions this version would give,
so what's yours starts ticked whatever made the backup. Pure, apart from
reading this version's known.json.
"""

import json
from pathlib import Path

KNOWN = Path(__file__).resolve().parent.parent / "audit" / "known.json"


def _known() -> dict:
    try:
        return json.loads(KNOWN.read_text())
    except (OSError, ValueError):
        return {}


def today(changes: dict, known: dict | None = None) -> dict:
    """The changes, each row's suggestion as this version gives it."""
    known = _known() if known is None else known
    settings = {s["id"]: s.get("suggest") for s in known.get("settings", [])}
    apps, hidden = known.get("apps", {}), known.get("hidden", {})
    items = []
    for it in changes.get("items", []):
        kind, _, name = it.get("id", "").partition(":")
        now = it.get("suggest")
        if kind == "setting" and settings.get(name):
            now = settings[name]
        elif kind == "settings" and name.startswith("omarchy-config/"):
            now = "keep"                       # your own settings for an app
        elif kind == "app":
            head = (it.get("source", {}).get("refs") or [name])[0]
            k = next((apps[r] for r in it.get("source", {}).get("refs", []) if r in apps), None) or apps.get(head)
            if k and k.get("suggest"):
                now = k["suggest"]
            elif now == "you" and it.get("paths"):
                now = "keep"                   # an app with your settings, window icon or not
        elif kind == "hidden" and name in hidden:
            now = hidden[name].get("suggest", now)
        items.append({**it, "suggest": now} if now != it.get("suggest") else it)
    from omabackups.audit.pages import sort
    return sort({**changes, "items": items})            # D46: this version's pages too
