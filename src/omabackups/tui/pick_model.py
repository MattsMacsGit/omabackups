"""What the picker shows and does, without the screen (BUILD 7.2, agreed 7 Nov).

Home folders first page, System beside them. Each row: a mark (✓ all of it
backed up, • part of it, nothing = skipped), a colour (green in the backup
already, blue goes at the next backup, grey skipped), a size counting only
what's backed up, and a plain line explaining it. Space adds or removes a
skip rule; saving hands the lists to the root helper.
"""

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from omabackups.backup import skips
from omabackups.backup.check import human
from omabackups.tui import quick
from omabackups.tui.quick import QUICK

HIDDEN_IN_SYSTEM = {"home", "boot", "proc", "sys", "dev", "run", "tmp", "mnt", "media", "lost+found"}
PART_ROOT = {"home": Path("/home"), "system": Path("/")}


@dataclass(frozen=True)
class Node:
    part: str           # "home" or "system"
    rel: str            # path inside the part ("u/Videos"; "" = the part itself)
    name: str
    is_dir: bool

    def path(self, roots) -> Path:
        return roots[self.part] / self.rel if self.rel else roots[self.part]


def escape(name: str) -> str:
    """A name as a rule that matches only itself (rsync and fnmatch agree on [*])."""
    return "".join(f"[{c}]" if c in "*?[" else c for c in name)


class Model:
    def __init__(self, user: str, record: dict, roots=None, rules=None):
        self.user, self.record = user, record
        self.roots = roots or PART_ROOT
        self.rules = {p: list(rules[p] if rules else skips.patterns_for(p)) for p in ("home", "system")}
        # Each restore point with the skip list it was made with (kept by the backup):
        # the colours say what your backup holds (§7.2).
        made = record.get("point_skips") or {}
        if not made and record.get("last_point"):
            made = {record["last_point"]: {"time": record.get("last_finished", 0),
                                           "skips": record.get("skip_patterns") or {}}}
        self.points = [(n, v.get("time", 0), {p: skips.Skips((v.get("skips") or {}).get(p, []))
                                              for p in ("home", "system")}) for n, v in made.items()]
        self.latest = record.get("last_point")
        latest = next((r for n, _, r in self.points if n == self.latest), None)
        self.before = latest or {p: skips.Skips(self.rules[p]) for p in ("home", "system")}
        self.backed_up_once = bool(record.get("last_finished"))
        self.dirty = False
        self.show_hidden = False    # hidden files: Migrate's business; H shows them
        self._sizes, self._inside, self._lock, self._held = {}, {}, threading.Lock(), {}
        # The size on the computer, skipped or not: the rows' order. Ticking
        # never changes it, so rows don't jump about (they sorted by the
        # backed-up size, which drops to 0 when a row is skipped).
        self._disk = {}
        self._refresh()

    def _refresh(self) -> None:
        self.skips = {p: skips.Skips(r) for p, r in self.rules.items()}

    # --- the pages ---------------------------------------------------------

    def home(self) -> Node:
        return Node("home", self.user, "Home", True)

    def system(self) -> Node:
        """Measured for the total only: the system isn't browsed (Quick skips instead)."""
        return Node("system", "", "System", True)

    def quick(self) -> Node:
        return Node("quick", "", "Quick skips", True)

    def _quick(self, node: Node):
        return next(q for q in QUICK if q.id == node.rel)

    def _present(self, node: Node) -> tuple[int, int, bool]:
        """(how many of this switch's rules are in the list, how many it has,
        were any in the list at the last backup)."""
        mine = quick.rules(self._quick(node), self.user)
        have = sum(r in self.rules[p] for p, rs in mine.items() for r in rs)
        before = any(r in self.before[p].patterns for p, rs in mine.items() for r in rs)
        return have, sum(len(rs) for rs in mine.values()), before

    def listing(self, node: Node) -> list[Node]:
        """What the screen shows: hidden (dot) files only when asked (H).
        Sizes still count them: they're backed up like anything else."""
        rows = self.children(node)
        if self.show_hidden:
            return rows
        return [n for n in rows if not n.name.startswith(".") or n.part == "quick"]

    def children(self, node: Node) -> list[Node]:
        if node == self.quick():
            return [Node("quick", q.id, q.label, False) for q in QUICK]
        out = []
        try:
            entries = list(os.scandir(node.path(self.roots)))
        except OSError:
            entries = []
        for e in entries:
            if node.part == "system" and not node.rel and e.name in HIDDEN_IN_SYSTEM:
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            out.append(Node(node.part, f"{node.rel}/{e.name}".lstrip("/"), e.name, is_dir))
        if node == self.home():
            out.append(self.quick())
        # Folders before files, each biggest on the computer first (never by
        # what's ticked); hidden ones after; Quick skips last.
        key = lambda n: (n.part == "quick", n.name.startswith("."), not n.is_dir,  # noqa: E731
                         -(self.disk_size(n) or 0), n.name.lower())
        return sorted(out, key=key)

    # --- what a row says -----------------------------------------------------

    def skipped(self, node: Node) -> bool:
        if node.part == "quick":
            if not node.rel:
                return False
            have, total, _ = self._present(node)
            return have == total
        return bool(node.rel) and self.skips[node.part].skipped(node.rel)

    def inside_skipped(self, node: Node) -> int:
        """How many things inside are skipped (found while measuring)."""
        with self._lock:
            return self._inside.get(node, 0)

    def held(self, node: Node, latest_only: bool) -> bool:
        """Is it in your latest restore point (or in any)? Not skipped by that
        point's list, and there already when it was made."""
        key = (node, latest_only)
        if key not in self._held:
            self._held[key] = any(self._held_by(node, when, rules)
                                  for name, when, rules in self.points
                                  if not latest_only or name == self.latest)
        return self._held[key]

    def _held_by(self, node: Node, when: float, rules: dict) -> bool:
        if node.part == "quick":      # one of its real folders wasn't skipped by that point
            for place in quick.places(self._quick(node), self.user, self.roots):
                for part, root in self.roots.items():
                    rel = os.path.relpath(place, root)
                    if not rel.startswith("..") and part in rules and not rules[part].skipped(rel) \
                            and self._older(Path(place), when):
                        return True
            return False
        if node.rel and rules[node.part].skipped(node.rel):
            return False
        return self._older(node.path(self.roots), when)

    @staticmethod
    def _older(path: Path, when: float) -> bool:
        """There before `when`: itself, or (a folder) something in it."""
        try:
            if os.lstat(path).st_mtime <= when:
                return True
            if path.is_dir() and not path.is_symlink():
                for n, entry in enumerate(os.scandir(path)):
                    if n > 200:
                        break
                    if entry.stat(follow_symlinks=False).st_mtime <= when:
                        return True
        except OSError:
            pass
        return False

    def mark(self, node: Node) -> str:
        if node.part == "quick":
            if not node.rel:
                return "•" if any(self._present(n)[0] for n in self.children(node)) else "✓"
            have, total, _ = self._present(node)
            return " " if have == total else "•" if have else "✓"
        if self.skipped(node):
            return " "
        return "•" if node.is_dir and self.inside_skipped(node) else "✓"

    def colour(self, node: Node) -> str:
        """Tick = backed up from now on; colour = what your backup holds (§7.2):
        green ticked and in the latest point; blue ticked, not in yet; yellow not
        ticked but in older restore points; grey in none."""
        if node in (self.home(), self.quick()):
            return "green" if self.backed_up_once else "blue"
        if self.skipped(node):
            return "yellow" if self.held(node, latest_only=False) else "grey"
        return "green" if self.held(node, latest_only=True) else "blue"

    def explain(self, node: Node) -> str:
        if node == self.quick():
            return ("Quick skips: big things you may not need backed up. The rest of the system "
                    "is always backed up (the Rescue USB needs it).")
        if node.part == "quick":
            have, total, _ = self._present(node)
            state = ("Part of it is skipped: Space skips all of it." if 0 < have < total
                     else self._state_line(node, "them"))
            return f"{node.name}: {self._quick(node).note} {state}"
        why = node.rel and self.skips[node.part].why(node.rel)
        if why:
            rule, folder = why
            if folder != node.rel:
                name = folder.split('/')[-1]
                return f"{node.name}: inside {name}, which is skipped. Tick {name} to back it up."
            if not rule.startswith("/"):
                return (f"{node.name}: skipped, like every {rule.split('/')[-1]} (caches and the trash "
                        "aren't backed up). Space backs this one up anyway.")
            return f"{node.name}: {self._state_line(node, 'it')}"
        n = self.inside_skipped(node)
        if n:
            return f"{node.name}: {n} thing{'s' if n > 1 else ''} inside {'are' if n > 1 else 'is'} skipped. Open it to see."
        if self.colour(node) == "blue":
            return f"{node.name}: goes in at the next backup."
        return f"{node.name}: everything in it is backed up." if node.is_dir else f"{node.name}: backed up."

    def _state_line(self, node: Node, it: str) -> str:
        colour = self.colour(node)
        if colour == "yellow":
            return (f"Not backed up any more, but in your older restore points until thinning "
                    f"removes them (a kept restore point holds on to {it}). Space backs {it} up again.")
        if colour == "grey":
            return f"Skipped: not in your backup. Space backs {it} up."
        if colour == "blue":
            return f"Goes in at the next backup. Space skips {it}."
        return f"Backed up. Space skips {it}."

    # --- Space ---------------------------------------------------------------

    def toggle(self, node: Node) -> str | None:
        """Tick or skip; returns a message when it can't."""
        if node in (self.system(), self.home(), self.quick()):
            return "Open it to choose what's inside."
        if node.part == "quick":
            have, total, _ = self._present(node)
            for part, rs in quick.rules(self._quick(node), self.user).items():
                for r in rs:
                    if have == total and r in self.rules[part]:
                        self.rules[part].remove(r)       # all skipped: back them up
                    elif have < total and r not in self.rules[part]:
                        self.rules[part].append(r)       # skip all of it
            self.dirty = True
            self._refresh()
            with self._lock:                            # sizes everywhere may change
                for n in [n for n in self._sizes if n.part != "quick"]:
                    self._sizes.pop(n, None)
                    self._inside.pop(n, None)
            return None
        rules, me = self.rules[node.part], "/" + "/".join(escape(p) for p in node.rel.split("/"))
        why = self.skips[node.part].why(node.rel)
        if why:
            rule, folder = why
            if folder != node.rel:
                name = folder.split('/')[-1]
                return f"It's inside {name}, which is skipped: tick {name} to back it up."
            if rule == me:
                rules.remove(rule)
            else:
                rules.append("!" + me)          # skipped everywhere, but back this one up
        elif "!" + me in rules:
            rules.remove("!" + me)
        else:
            rules.append(me)
        self.dirty = True
        self._refresh()
        self._forget(node)
        return None

    # --- sizes (what's backed up), measured in the background ---------------

    def size(self, node: Node) -> int | None:
        with self._lock:
            return self._sizes.get(node)

    def disk_size(self, node: Node) -> int | None:
        """The size on the computer, ticked or not (for the order)."""
        with self._lock:
            return self._disk.get(node)

    def measure(self, node: Node, stop=lambda: False) -> int:
        """Size of what's backed up under node (0 if skipped); counts skips inside.
        A Quick skip's size is what it holds, skipped or not (what skipping saves)."""
        if node.part == "quick":
            items = self.children(node) if node == self.quick() else [node]
            for item in items:
                if stop():
                    return 0
                got = quick.size(quick.places(self._quick(item), self.user, self.roots))
                with self._lock:
                    self._sizes[item] = got
            return 0
        skipped = self.skipped(node)
        if not node.is_dir:
            try:
                total = os.lstat(node.path(self.roots)).st_size
            except OSError:
                total = 0
            with self._lock:
                self._disk[node] = total
                self._sizes[node] = 0 if skipped else total
            return 0 if skipped else total
        total, disk, inside = 0, 0, 0
        for child in self.children(node) if node != self.home() else self.children_plain(node):
            if stop():
                return total
            if self.size(child) is None or self.disk_size(child) is None:
                self.measure(child, stop)
            total += self.size(child) or 0
            disk += self.disk_size(child) or 0
            inside += 1 if self.skipped(child) else self.inside_skipped(child)
        with self._lock:
            self._sizes[node], self._inside[node] = (0 if skipped else total), inside
            self._disk[node] = disk
        return 0 if skipped else total

    def children_plain(self, node: Node) -> list[Node]:
        return [c for c in self.children(node) if c.part != "quick"]

    def _forget(self, node: Node) -> None:
        """A rule changed at node: its size and every folder above it again."""
        with self._lock:
            for n in list(self._sizes):
                if n.part == node.part and (n.rel == node.rel or n.rel.startswith(node.rel + "/")
                                           or node.rel.startswith(n.rel + "/") or not n.rel):
                    self._sizes.pop(n, None)
                    self._inside.pop(n, None)
            for n in (self.home(), self.system()):
                if n.part == node.part:           # only the part that changed
                    self._sizes.pop(n, None)
                    self._inside.pop(n, None)

    # --- the bottom line ---------------------------------------------------------

    def total(self) -> int | None:
        h, s = self.size(self.home()), self.size(self.system())
        return None if h is None or s is None else h + s

    def bottom(self) -> tuple[str, bool]:
        """("Backing up 305 GB · your backup has 1.8 TB free", fits?)."""
        space, total = self.record.get("space") or {}, self.total()
        shown = human(total) if total is not None else "…"
        if not space.get("free"):
            return f"Backing up {shown}", True
        fits = total is None or total <= (space.get("used") or 0) + space["free"]
        return f"Backing up {shown} · your backup has {human(space['free'])} free", fits

    def to_save(self) -> dict:
        return {p: list(r) for p, r in self.rules.items()}

