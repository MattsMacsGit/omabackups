"""From what was ticked in Choose what comes over to a list of jobs (6.1 F).

Reads only the restore point's changes.json (the audit's neutral format,
D21), never the old system itself. Pure: nothing here changes anything.
"""

import re

# A tool's reinstall command, as the audit wrote it, run only if it's exactly
# one of these shapes (1.x rule: nothing else from a backup is ever run).
TOOL = re.compile(r"^(uv tool install|npm install -g|pipx install|cargo install|mise use -g) "
                  r"[A-Za-z0-9@._/:+=-]+$")
PACKAGE = re.compile(r"^[a-z0-9@._+-]+$")
FLATPAK = re.compile(r"^[A-Za-z0-9._-]+$")


def pages(changes: dict) -> list[dict]:
    """The picker's pages: each group that has something in it, in order."""
    out = []
    for group in changes.get("groups", []):
        items = [i for i in changes.get("items", []) if i.get("group") == group["id"]]
        if items:
            out.append({"id": group["id"], "title": group["title"], "items": items})
    return out


def suggested(changes: dict) -> set[str]:
    """What starts ticked: everything suggested Keep (D14)."""
    return {i["id"] for i in changes.get("items", []) if i.get("suggest") == "keep"}


def jobs(changes: dict, picked: set[str]) -> dict:
    out = {"packages": [], "flatpaks": [], "tools": [], "home": [], "system": [], "units": [],
           "files": [], "restart": False, "skipped": []}
    for item in changes.get("items", []):
        if item["id"] not in picked:
            continue
        kind = item.get("source", {}).get("kind")
        refs = item.get("source", {}).get("refs", [])
        if kind == "package":
            out["packages"] += [r for r in refs if PACKAGE.match(r) and r not in out["packages"]]
        elif kind == "flatpak":
            out["flatpaks"] += [r for r in refs if FLATPAK.match(r)]
        elif kind == "tool":
            hint = item.get("reinstall", "")
            if TOOL.match(hint):
                out["tools"].append({"name": item["name"], "command": hint})
            else:
                out["skipped"].append(f"{item['name']}: install it again by hand ({hint or 'no command known'})")
        for path in item.get("paths", []):
            if item.get("group") == "files":
                out["files"].append(path.removeprefix("~/"))
            elif path.startswith("~/"):
                out["home"].append(path)
            elif path.startswith("/"):
                out["system"].append(path)
        out["units"] += [u for u in item.get("units", []) if isinstance(u, dict)]
        out["restart"] = out["restart"] or bool(item.get("restart"))
    return out


def summary(job: dict) -> str:
    apps = len(job["packages"]) + len(job["flatpaks"]) + len(job["tools"])
    bits = [f"{apps} app{'s' if apps != 1 else ''}", f"{len(job['home']) + len(job['system'])} settings"]
    if job["files"]:
        bits.append(f"{len(job['files'])} folder{'s' if len(job['files']) != 1 else ''} of your files")
    return ", ".join(bits)
