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
        self.before = {p: skips.Skips((record.get("skip_patterns") or {}).get(p, self.rules[p]))
                       for p in ("home", "system")}
        self.backed_up_once = bool(record.get("last_finished"))
        self.dirty = False
        self._sizes, self._inside, self._lock = {}, {}, threading.Lock()
        self._refresh()

    def _refresh(self) -> None:
        self.skips = {p: skips.Skips(r) for p, r in self.rules.items()}

    # --- the pages ---------------------------------------------------------

    def home(self) -> Node:
        return Node("home", self.user, "Home", True)

    def system(self) -> Node:
        return Node("system", "", "System", True)

    def children(self, node: Node) -> list[Node]:
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
            out.append(self.system())
        # Visible folders biggest first, then hidden ones, then System last (as agreed).
        key = lambda n: (n == self.system(), n.name.startswith("."),  # noqa: E731
                         -(self.size(n) or 0), n.name.lower())
        return sorted(out, key=key)

    # --- what a row says -----------------------------------------------------

    def skipped(self, node: Node) -> bool:
        return bool(node.rel) and self.skips[node.part].skipped(node.rel)

    def inside_skipped(self, node: Node) -> int:
        """How many things inside are skipped (found while measuring)."""
        with self._lock:
            return self._inside.get(node, 0)

    def mark(self, node: Node) -> str:
        if self.skipped(node):
            return " "
        return "•" if node.is_dir and self.inside_skipped(node) else "✓"

    def colour(self, node: Node) -> str:
        if self.skipped(node):
            return "grey"
        if not self.backed_up_once or (node.rel and self.before[node.part].skipped(node.rel)):
            return "blue"
        return "green"

    def explain(self, node: Node) -> str:
        why = node.rel and self.skips[node.part].why(node.rel)
        if why:
            rule, folder = why
            if folder != node.rel:
                return f"{node.name}: inside {folder.split('/')[-1]}, which is skipped. Tick that first."
            if not rule.startswith("/"):
                return (f"{node.name}: skipped, like every {rule.split('/')[-1]} (caches and the trash "
                        "aren't backed up). Space backs this one up anyway.")
            return f"{node.name}: skipped. Space backs it up again."
        n = self.inside_skipped(node)
        if n:
            return f"{node.name}: {n} thing{'s' if n > 1 else ''} inside {'are' if n > 1 else 'is'} skipped. Open it to see."
        if self.colour(node) == "blue":
            return f"{node.name}: backed up from the next backup on."
        return f"{node.name}: everything in it is backed up." if node.is_dir else f"{node.name}: backed up."

    # --- Space ---------------------------------------------------------------

    def toggle(self, node: Node) -> str | None:
        """Tick or skip; returns a message when it can't."""
        if node == self.system() or node == self.home():
            return "Open it to choose what's inside."
        rules, me = self.rules[node.part], "/" + "/".join(escape(p) for p in node.rel.split("/"))
        why = self.skips[node.part].why(node.rel)
        if why:
            rule, folder = why
            if folder != node.rel:
                return f"It's inside {folder.split('/')[-1]}, which is skipped. Tick that first."
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

    def measure(self, node: Node, stop=lambda: False) -> int:
        """Size of what's backed up under node (0 if skipped); counts skips inside."""
        if self.skipped(node):
            return 0
        if not node.is_dir:
            try:
                total = os.lstat(node.path(self.roots)).st_size
            except OSError:
                total = 0
            with self._lock:
                self._sizes[node] = total
            return total
        total, inside = 0, 0
        for child in self.children(node) if node != self.home() else self.children_plain(node):
            if stop():
                return total
            known = self.size(child)
            got = known if known is not None else self.measure(child, stop)
            total += got
            inside += 1 if self.skipped(child) else self.inside_skipped(child)
        with self._lock:
            self._sizes[node], self._inside[node] = total, inside
        return total

    def children_plain(self, node: Node) -> list[Node]:
        return [c for c in self.children(node) if c != self.system()]

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

