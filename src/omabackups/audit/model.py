"""The audit's neutral format: "Your changes to Omarchy" (D9, D21).

What a system has on top of a fresh install, described without the source
system's words where it can: "Firefox, with its profile here", not "the Arch
package firefox". The source's own names (package, Flatpak id...) sit in
`source`, so a later version can read audits from other systems (D21).
Migrate reads only this, never the old system (stage 8).

changes.json = {
  "format": 1, "made": time, "source": {"system": "omarchy", "version": "4.5.0-3"},
  "user": "...", "groups": [{"id", "title"}], "items": [item...], "notes": {...}
}
item = {
  "id": "app:firefox", "group": "apps", "name": "Firefox",
  "what": "what it is", "why": "why keep it (or not)", "back": "how easy to get back without it",
  "suggest": "keep" | "you" | "leave", "weight": 0-100 (higher first),
  "source": {"kind": "package" | "flatpak" | "webapp" | "file" | "config" | "folder", "refs": [...]},
  "paths": ["~/.mozilla/firefox"], "bytes": 123 | null, "needs_admin": false,
  "restart": false, "units": []
}
"""

import time

FORMAT = 1

# The picker's pages, in order (D46: audit/pages.py sorts each row onto one).
from omabackups.audit.pages import GROUPS, OLD, sort  # noqa: E402
SUGGEST = ("keep", "you", "leave")


def item(id: str, group: str, name: str, kind: str, refs=(), paths=(), suggest: str = "you",
         weight: float = 30, what: str = "", why: str = "", back: str = "", **extra) -> dict:
    assert (group in dict(GROUPS) or group in OLD) and suggest in SUGGEST
    return {"id": id, "group": group, "name": name, "what": what, "why": why, "back": back,
            "suggest": suggest, "weight": round(float(weight), 1),
            "source": {"kind": kind, "refs": list(refs)}, "paths": list(paths),
            "bytes": extra.pop("bytes", None), "needs_admin": extra.pop("needs_admin", False),
            "restart": extra.pop("restart", False), "units": extra.pop("units", []), **extra}


def audit(source: dict, user: str, items: list, notes: dict) -> dict:
    return sort({"format": FORMAT, "made": int(time.time()), "source": source, "user": user,
                 "items": items, "notes": notes})


def summary(audit_: dict) -> str:
    """Plain text, for `omabackups changes`."""
    lines = []
    for g in audit_["groups"]:
        mine = [i for i in audit_["items"] if i["group"] == g["id"]]
        if not mine:
            continue
        lines.append(f"\n{g['title']} ({len(mine)})")
        for i in mine:
            size = f"  [{human(i['bytes'])}]" if i.get("bytes") else ""
            lines.append(f"  {i['name']}{size}")
            if i.get("what"):
                lines.append(f"      {i['what']}")
    return "\n".join(lines).lstrip("\n")


def human(n: int | None) -> str:
    if not n:
        return ""
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1000
    return ""
