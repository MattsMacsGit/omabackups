"""Choose what comes back (D52): the picker the other way round, for Restore
my files after a Quick Rescue (as in 1.x, where the same picker kept a
"leave out of Restore my files" list).

The same screen, rows, sizes, keys and Quick skips as Choose what gets backed
up (D12), but on your home folder as it is in the restore point, opened
read-only as Browse does (D37). A tick means "bring it back"; the colours say
what's here: blue comes back, green already here (anything missing comes
back; a file that's newer here is kept), grey stays in your backup. Saving
starts Restore my files with what's left unticked left out. It can be opened
and run again as often as you like.

`omabackups restore-files <point> --pick` opens it (the panel's Restore my files).
"""

import curses
import getpass
import os
import shutil
from pathlib import Path

from omabackups.backup.check import human
from omabackups.core import rootjob, state
from omabackups.core.errors import OmaError
from omabackups.tui.pick_model import Model, Node

KEYS = "↑↓ move  Enter open  ⌫/Esc back  Space tick  h hidden  s bring back  q quit"
NOTE = "Tick what to bring back, then press s: it comes back while you work."
STATE = "bring-back"          # the last choices, per restore point


class BringBack(Model):
    def __init__(self, user: str, point_home: Path, here: Path, rules: list[str] | None = None,
                 system_rules: list[str] | None = None):
        """user: the home folder's name in the restore point; point_home: the
        restore point's /home, opened read-only; here: this computer's home."""
        super().__init__(user, {}, roots={"home": point_home, "system": point_home.parent / "system"},
                         rules={"home": list(rules or []), "system": list(system_rules or [])})
        self.here = here

    def _local(self, node: Node) -> Path:
        rel = node.rel.split("/", 1)[1] if "/" in node.rel else ""
        return self.here / rel if rel else self.here

    def _already_here(self, node: Node) -> bool:
        local = self._local(node)
        try:
            if node.is_dir:
                return local.is_dir()
            return os.lstat(local).st_size == os.lstat(node.path(self.roots)).st_size
        except OSError:
            return False

    def colour(self, node: Node) -> str:
        if node in (self.home(), self.quick()):
            return "blue"
        if node.part == "quick":
            return "grey" if self.skipped(node) else "blue"
        if self.skipped(node):
            return "grey"
        return "green" if self._already_here(node) else "blue"

    def explain(self, node: Node) -> str:
        if node == self.quick():
            return "Quick skips: big things you may not need back yet. They stay in your backup."
        if node.part == "quick":
            have, total, _ = self._present(node)
            state_line = ("Part of it stays in your backup: Space leaves all of it." if 0 < have < total
                          else "Stays in your backup: Space brings it back." if have == total
                          else "Comes back: Space leaves it in your backup.")
            return f"{node.name}: {self._quick(node).note} {state_line}"
        why = node.rel and self.skips[node.part].why(node.rel)
        if why:
            rule, folder = why
            if folder != node.rel:
                name = folder.split("/")[-1]
                return f"{node.name}: inside {name}, which stays in your backup. Tick {name} to bring it back."
            return f"{node.name}: stays in your backup. Space brings it back."
        n = self.inside_skipped(node)
        if n:
            return (f"{node.name}: {n} thing{'s' if n > 1 else ''} inside "
                    f"{'stay' if n > 1 else 'stays'} in your backup. Open it to see.")
        if self.colour(node) == "green":
            return (f"{node.name}: already here; anything missing comes back, and a file that's "
                    "newer here is kept." if node.is_dir else f"{node.name}: already here.")
        return f"{node.name}: comes back."

    def total(self) -> int | None:
        return self.size(self.home())

    def bottom(self) -> tuple[str, bool]:
        total = self.total()
        try:
            free = shutil.disk_usage(self.here).free
        except OSError:
            return f"Bringing back {human(total) if total is not None else '…'}", True
        fits = total is None or total <= free
        return (f"Bringing back {human(total) if total is not None else '…'} · "
                f"this computer has {human(free)} free"), fits

    def leave_out(self) -> list[str]:
        """The rules, relative to the home folder (what Restore my files reads)."""
        mine = f"/{self.user}"
        out = []
        for rule in self.rules["home"]:
            keep, body = rule.startswith("!"), rule.removeprefix("!")
            if body.startswith(mine + "/"):
                body = body[len(mine):]
            elif body.startswith("/"):
                continue                 # another home's: not in this restore
            out.append(("!" if keep else "") + body)
        return out


class BringBackMode:
    title = "Choose what comes back"
    skipped_word = "left in backup"
    hidden_off = "Hidden files aren't shown (your settings came back with the rescue)."
    keys, note = KEYS, NOTE
    question = "Bring back what's ticked?"

    def __init__(self, point: str, request: dict):
        self.point, self.request = point, request

    def measured(self, model: Model) -> tuple:
        return (model.home(), model.quick())

    def save(self, model: BringBack) -> str | None:
        state.write(STATE, {"point": self.point, "rules": model.rules["home"],
                            "system_rules": model.rules["system"]})
        rootjob.run("browse-close", {})
        try:
            # Quick skips in the system area (AI models and the like, audit 8.4) left in the backup too.
            rootjob.run("restore-files-start", {**self.request, "leave_out": model.leave_out(),
                                                "leave_out_system": model.rules["system"]})
        except OmaError as exc:
            return exc.what
        return None


def run(point: str, request: dict, events) -> int:
    from omabackups.tui.picker import Picker
    if not (os.isatty(0) and os.isatty(1)):
        raise OmaError("Choose what comes back needs a terminal window.",
                       "Run omabackups restore-files <restore point> --pick in a terminal "
                       "(the panel opens one for it).", code="no-terminal")
    events.message("Opening the restore point (read-only)...")
    opened = rootjob.run("browse-open", {"point": point})
    path = Path(opened["path"])
    try:
        last = state.read(STATE) or {}
        mine = last.get("point") == point
        model = BringBack(path.name, path.parent, Path.home(), last.get("rules") if mine else None,
                          last.get("system_rules") if mine else None)
        saved = curses.wrapper(lambda scr: Picker(scr, model, mode=BringBackMode(point, request)).run())
    finally:
        rootjob.run("browse-close", {})
    events.result({"saved": saved, "user": getpass.getuser()},
                  "Bringing your files back. A file that's newer here is never overwritten. "
                  "The panel shows how it's going." if saved else "Nothing was changed.")
    return 0
