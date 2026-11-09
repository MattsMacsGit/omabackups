"""Keybindings, bar & theme: merged onto this Omarchy, never copied (D43).

Built from the 5 Nov 1.x test, where it was done by hand and worked:
- A Hyprland file (bindings.lua, input.lua...): this install's file stays.
  "Your own lines" are what you changed in the OLD Omarchy's stock file (it's
  in the restore point, so any older release works, D42). A block you added
  goes in after the line it followed (or at the end); a stock line you
  changed is changed here too, if this release still has it. A change that
  can't be placed is never forced: it's listed to look at.
  A setting that is a comma list (kb_options) keeps this release's values
  and adds yours: the new default isn't lost to the old one.
- shell.json (the bar): what you changed from the old stock is yours; what
  this release added (a dock, a new widget) stays; plugins you didn't bring
  over are left out of the layout.

Pure: text in, text out.
"""

import difflib
import json
import re

ASSIGN = re.compile(r'^(\s*)([A-Za-z_][\w.]*)\s*=\s*"([^"]*)"(\s*,?\s*)$')
BLANK = re.compile(r"^\s*(--.*)?$")


def _comma_join(stock_line: str, mine: str, new_line: str) -> str | None:
    """kb_options = "a,b": this release's values, plus the ones you added."""
    s, m, n = ASSIGN.match(stock_line), ASSIGN.match(mine), ASSIGN.match(new_line)
    if not (s and m and n) or not (s.group(2) == m.group(2) == n.group(2)) or "," not in m.group(3) + s.group(3):
        return None
    old = [x for x in s.group(3).split(",") if x]
    added = [x for x in m.group(3).split(",") if x and x not in old]
    values = [x for x in n.group(3).split(",") if x] + [x for x in added if x not in n.group(3).split(",")]
    return f'{n.group(1)}{n.group(2)} = "{",".join(values)}"{n.group(4)}'


def lua(old_stock: str | None, old_mine: str, new: str) -> tuple[str, list[str]]:
    """Your own changes to a Hyprland file, made to this release's file.
    Returns (the merged text, the changes that couldn't be placed)."""
    base = (old_stock or "").splitlines()
    mine = old_mine.splitlines()
    out = new.splitlines()
    unplaced: list[str] = []
    tail: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base, mine, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        ours = mine[j1:j2]
        if tag == "delete" or all(BLANK.match(x) and not x.strip().startswith("--") for x in ours) and tag == "insert":
            continue          # a stock line you removed, or only blank lines: nothing to bring
        if _already(out, ours):
            continue          # D44: already in this file (Migrate run again): never twice
        if tag == "insert":
            anchor = base[i1 - 1] if i1 > 0 else None
            if anchor is not None and anchor.strip() and anchor in out and i1 < len(base):
                at = out.index(anchor) + 1
                out[at:at] = ours
            else:
                tail += ours
            continue
        # replace: a stock line you changed
        theirs = base[i1:i2]
        at = _find(out, theirs)
        if at is not None:
            out[at:at + len(theirs)] = ours
        elif len(theirs) == len(ours) == 1:
            key = ASSIGN.match(ours[0])
            spot = next((k for k, x in enumerate(out) if key and ASSIGN.match(x) and
                         ASSIGN.match(x).group(2) == key.group(2)), None)
            joined = _comma_join(theirs[0], ours[0], out[spot]) if spot is not None else None
            if joined:
                out[spot] = joined
            elif all(x.strip().startswith("--") for x in theirs):
                tail += ours          # you un-commented an example this release no longer has
            else:
                unplaced += ours
        elif all(x.strip().startswith("--") or not x.strip() for x in theirs):
            tail += ours
        else:
            unplaced += ours
    if any(x.strip() for x in tail):
        out += ["", "-- Brought over from your old system by OmaBackups Migrate."] + tail
    return "\n".join(out) + "\n", [x for x in unplaced if x.strip()]


def _already(lines: list[str], block: list[str]) -> bool:
    """The block is in the file already, and it says something (a line with a
    letter or digit that isn't a comment), so a lone "}" never counts."""
    core = [x for x in block if x.strip()]
    meaningful = any(re.search(r"\w", x) and not x.strip().startswith("--") for x in core)
    return bool(core) and meaningful and _find([x for x in lines if x.strip()], core) is not None


def _find(lines: list[str], block: list[str]) -> int | None:
    for k in range(len(lines) - len(block) + 1):
        if lines[k:k + len(block)] == block:
            return k
    return None


def _ids(items) -> list:
    return [x.get("id") for x in items if isinstance(x, dict)]


def _list(stock: list, mine: list, new: list, keep) -> list:
    if not (all(isinstance(x, dict) and "id" in x for x in mine + new)):
        return mine
    out = [x for x in mine if keep(x["id"])]
    have, old = set(_ids(out)), set(_ids(stock))
    out += [x for x in new if x["id"] not in old and x["id"] not in have and x["id"] not in _ids(mine)]
    return out


def json_(stock, mine, new, keep):
    """The bar: yours where you changed it, this release's everywhere else.
    keep(id) says whether a widget or plugin stays (it's here, or Omarchy's)."""
    if mine == stock:
        return new
    if isinstance(mine, dict) and isinstance(new, dict):
        stock = stock if isinstance(stock, dict) else {}
        out = dict(new)
        for k, v in mine.items():
            out[k] = json_(stock.get(k), v, new.get(k), keep) if k in new else v
        return out
    if isinstance(mine, list) and isinstance(new, list):
        return _list(stock if isinstance(stock, list) else [], mine, new, keep)
    return mine


def shell(old_stock: str | None, old_mine: str, new: str, keep) -> str:
    merged = json_(json.loads(old_stock) if old_stock else None, json.loads(old_mine), json.loads(new), keep)
    return json.dumps(merged, indent=2) + "\n"
