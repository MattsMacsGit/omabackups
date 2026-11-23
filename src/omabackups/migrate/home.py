"""Migrate's steps inside the home folder (D59). These run only as the user,
through core/asuser.py: never import them into a root job and call them.

Each takes and returns plain JSON values (paths as text)."""

import os
import shutil
from pathlib import Path

from omabackups.migrate import merge as merging
from omabackups.migrate import rename as renaming

# Where Omarchy keeps the theme in use: since June 2026 in ~/.local/state,
# before that in ~/.config (D42: any release). Read from whichever is there.
THEME_PLACES = (".local/state/omarchy/current", ".config/omarchy/current")


def keep_first(listing: str, dest: str, keep: str) -> None:
    """D45: the files here that the fetch will replace, copied aside first."""
    from omabackups.migrate import apply
    apply.keep_first(listing, Path(dest), Path(keep))


def _text(path: Path) -> str | None:
    return path.read_text(errors="replace") if path.is_file() else None


def merge(home: str, root: str, stage: str, items: list[dict]) -> dict:
    """Keybindings, bar & theme (D43): each file merged onto this release's.
    stage holds the old file (home/) and the old release's stock one (system/)."""
    home_, root_, stage_ = Path(home), Path(root), Path(stage)
    done, problems = [], []
    plugins = _plugins(home_)
    keep = lambda wid: str(wid).startswith("omarchy.") or wid in plugins  # noqa: E731
    for i in items:
        mine = _text(stage_ / "home" / i["path"])
        if mine is None:
            continue
        stock = _text(stage_ / "system" / i["stock"])
        here = home_ / i["path"]
        new = _text(here) if here.is_file() else _text(root_ / i["stock"])
        new = new or ""
        try:
            if i["kind"] == "json":
                text, unplaced = merging.shell(stock, mine, new or mine, keep), []
            else:
                text, unplaced = merging.lua(stock, mine, new)
        except ValueError as exc:
            problems.append({"what": f"~/{i['path']} couldn't be merged; yours is kept as "
                                     f"~/{i['path']}.from-old-system to look at.", "details": str(exc)})
            text, unplaced = None, []
        if text is None or not text.strip():
            _write(home_ / (i["path"] + ".from-old-system"), mine)
            continue
        before = home_ / (i["path"] + ".omabackups-before")
        if here.is_file() and not before.exists():      # D44: the first merge's, kept
            _write(before, here.read_text(errors="replace"))
        _write(here, text)
        done.append(i["path"])
        if unplaced:
            problems.append({"what": f"Some of your changes to ~/{i['path']} don't fit this Omarchy; "
                                     "they're listed here to add by hand if you still want them.",
                             "details": "\n".join(unplaced)})
    return {"done": done, "problems": problems}


def _plugins(home: Path) -> set:
    import json
    ids = set()
    for manifest in (home / ".config/omarchy/plugins").glob("*/manifest.json"):
        try:
            ids.add(json.loads(manifest.read_text()).get("id"))
        except (OSError, ValueError):
            pass
    return ids


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".omabackups-tmp")
    tmp.unlink(missing_ok=True)
    tmp.write_text(text)
    os.replace(tmp, path)


def theme(where: str) -> dict:
    """The old theme's name and background, from either layout."""
    for place in THEME_PLACES:
        base = Path(where) / place
        name_file, link, bg = base / "theme.name", base / "theme", base / "background"
        name = name_file.read_text().strip() if name_file.is_file() else \
            os.path.basename(os.readlink(link).rstrip("/")) if link.is_symlink() else ""
        if name:
            return {"name": name, "background": os.readlink(bg) if bg.is_symlink() else ""}
    return {}


def rename(home: str, items: list[str], old_home: str) -> dict:
    """The old user name fixed in what came over (D41, D44); sync apps later."""
    later: list[str] = []
    changed = renaming.fix(Path(home), items, old_home, later)
    changed += renaming.names(Path(home), items, old_home)
    return {"renamed": changed, "later": later}


def rename_later(home: str, files: list[str], old_home: str) -> list[str]:
    return renaming.fix(Path(home), files, old_home)


def missing(home: str, items: list[str]) -> list[str]:
    return [f"~/{i}" for i in items if not os.path.lexists(Path(home) / i)]


def kept(keep: str) -> bool:
    """D45: whether anything was kept aside; an empty folder is tidied away."""
    folder = Path(keep)
    if folder.is_dir() and any(folder.iterdir()):
        return True
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    return False


def histories(home: str, fetched: str, names: list[str]) -> list[str]:
    """D44: of these history files, the ones here that already carry the
    backup's past (fetched: the backup's copies)."""
    from omabackups.migrate.here import has_past
    out = []
    for name in names:
        try:
            old = (Path(fetched) / name).read_text(errors="replace")
            now = (Path(home) / name).read_text(errors="replace")
        except OSError:
            continue
        if has_past(old, now):
            out.append(name)
    return out
