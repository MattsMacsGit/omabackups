"""The pages of Choose what comes over, and which row goes on which (D46).

One place for it: the audit sorts a new backup's rows with it, and Migrate
sorts an older restore point's rows the same way (migrate/suggest.py), so
every point shows this version's pages.

Logins & keys first (what matters most), then Apps (with their settings),
Your desktop (keybindings, bar, theme and the desktop's extras),
Backgrounds (their own page, D43), Terminal & automation, System tweaks,
Your files.
"""

GROUPS = (
    ("logins", "Logins & keys"),
    ("apps", "Apps"),
    ("desktop", "Your desktop"),
    ("backgrounds", "Backgrounds"),
    ("terminal", "Terminal & automation"),
    ("tweaks", "System tweaks"),
    ("files", "Your files"),
)
# Older audits' page ids, still accepted when a row is made.
OLD = ("settings",)

LOGINS = {"ssh", "keyring", "gnupg", "gh", "git", "wifi", "bluetooth", "ai-agents"}
TERMINAL = {"shell", "local-bin"}
TWEAKS = {"printers"}


def group_of(item: dict) -> str:
    kind, _, name = item.get("id", "").partition(":")
    if kind == "setting":
        return "logins" if name in LOGINS else "terminal" if name in TERMINAL else \
            "tweaks" if name in TWEAKS else "apps"
    if kind in ("settings", "hidden", "app", "flatpak", "tool", "webapp"):
        return "apps"
    if kind == "extra":                       # D46: the desktop's extras and your automation
        return "terminal" if name in ("crontab", "user-services") else \
            "apps" if name == "flatpak-overrides" else "desktop"
    if kind in ("desktop", "backgrounds", "tweak", "files"):
        return {"tweak": "tweaks"}.get(kind, kind)
    return item.get("group") if item.get("group") in dict(GROUPS) else "apps"


def sort(changes: dict) -> dict:
    """Every row on this version's page; the pages in this version's order."""
    items = [{**i, "group": group_of(i)} for i in changes.get("items", [])]
    order = [g for g, _ in GROUPS]
    items.sort(key=lambda i: (order.index(i["group"]), -float(i.get("weight") or 0), i.get("name", "").lower()))
    return {**changes, "groups": [{"id": g, "title": t} for g, t in GROUPS], "items": items}
