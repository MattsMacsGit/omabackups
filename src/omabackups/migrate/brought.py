"""What Migrate has already brought over (D44): Run Migrate again shows those
rows as "Already in", never ticked, never brought twice.

Kept per backup line (the old computer's run of restore points, D22a): a
Migrate from another old computer starts fresh. Its own state file, so the
panel's flow (migrate.json) is never touched by it. Written only after the
run that brought them (lesson: state after the step succeeded).
"""

from omabackups.core import state

NAME = "migrated"      # {"lines": {"003": ["setting:shell", "files:Music", ...]}}


def line(point: str) -> str:
    """A restore point's backup line: 003-2026-11-09-1928 -> 003."""
    return point.split("-", 1)[0]


def newer(point: str, than: str | None) -> bool:
    """point is at least as new as `than` (none yet: yes). D45: the newest
    point Migrate came from stays the takeover's start."""
    from omabackups.backup.thinning import when
    if not than:
        return True
    a, b = when(point), when(than)
    return bool(a and b and a >= b)


def already(point: str) -> set[str]:
    saved = state.read(NAME) or {}
    return set(saved.get("lines", {}).get(line(point), []))


def record(point: str, ids) -> None:
    ids = set(ids)
    if not ids:
        return
    saved = state.read(NAME) or {}
    lines = dict(saved.get("lines", {}))
    lines[line(point)] = sorted(set(lines.get(line(point), [])) | ids)
    state.write(NAME, {**saved, "lines": lines})


def came_over(job: dict, picked, items: list[dict], files_now: bool) -> set[str]:
    """The ticked rows that really came over: not a tool left to install by
    hand, and folders only if they came back in this run (later ones are
    recorded by Restore my files' finish, through restored())."""
    by_id = {i["id"]: i for i in items}
    by_hand = {s.split(":", 1)[0] for s in job.get("skipped", [])}
    out = set()
    for pid in picked:
        it = by_id.get(pid)
        if not it or it.get("name") in by_hand:
            continue
        if it.get("group") == "files":
            folder = it["paths"][0].removeprefix("~/") if it.get("paths") else it.get("name")
            if not (files_now and folder in job.get("files", [])):
                continue
        out.add(pid)
    return out


def restored(migrate_state: dict | None) -> set[str]:
    """Folders Restore my files has finished bringing back for that Migrate."""
    m = migrate_state or {}
    return {f"files:{f}" for f in m.get("files", [])} if m.get("files_restored") else set()


def missed(came: set[str], here: set[str], items: list[dict]) -> list[dict]:
    """D45: the rows that were brought over but aren't here by the "is it
    here?" check (D44). Not checked: merged files (they never match the
    backup's), the theme in use (set again by name), folders (Restore my
    files has its own progress), rows with nothing to look at."""
    from omabackups.migrate import plan
    out = []
    for it in items:
        if it["id"] not in came or it["id"] in here or it.get("group") == "files":
            continue
        paths = it.get("paths", [])
        if any(plan.merge_kind(p) or plan.THEME.match(p) for p in paths):
            continue
        if not paths and it.get("source", {}).get("kind") not in ("package", "flatpak", "tool"):
            continue
        out.append(it)
    return out
