"""Choose what comes over (6.1 F step 3, D14, 7.2): the file selection's look,
one page per group (Apps, Settings, System tweaks, Keybindings, bar & theme,
Backgrounds, Your files). Suggestions start ticked; the line under the list
explains the highlighted one: what it is, why keep it, how easy it is to get
back without it. Your files has its own first row: now, or later.
"""

import curses
import os

from omabackups.backup.check import human
from omabackups.migrate import plan
from omabackups.tui import kit

KEYS = "↑↓ move  Space tick  ←→ pages  a all/none  s save & migrate  q quit"
SUGGEST = {"keep": "Keep", "you": "Up to you", "leave": "Leave"}
NOW_ROW = {"id": "@now", "name": "Bring them back now, in the same run (start it and walk away)"}


class Chooser:
    def __init__(self, scr, changes: dict, when: str, picked: set[str] | None = None):
        self.ui = kit.Screen(scr)
        self.pages = plan.pages(changes)
        self.picked = set(plan.suggested(changes) if picked is None else picked)
        self.files_now = True
        self.when, self.page, self.cursor, self.top = when, 0, {}, 0

    def rows(self) -> list[dict]:
        page = self.pages[self.page]
        return ([NOW_ROW] if page["id"] == "files" else []) + page["items"]

    def current(self) -> dict | None:
        rows = self.rows()
        return rows[min(self.cursor.get(self.page, 0), len(rows) - 1)] if rows else None

    def ticked(self, row: dict) -> bool:
        return self.files_now if row["id"] == "@now" else row["id"] in self.picked

    def draw(self) -> None:
        ui = self.ui
        ui.scr.erase()
        h, w = ui.size()
        page = self.pages[self.page]
        ui.header(f"Here's what you had installed as of: {self.when}",
                  f"{page['title']} ({self.page + 1} of {len(self.pages)})")
        rows, height = self.rows(), max(1, h - 2 - kit.Screen.BOTTOM)
        pos = min(self.cursor.get(self.page, 0), max(0, len(rows) - 1))
        self.top = min(self.top, pos) if pos < self.top else max(self.top, pos - height + 1)
        for i, row in enumerate(rows[self.top:self.top + height]):
            special = row["id"] == "@now"
            note = "" if special else SUGGEST.get(row.get("suggest"), "")
            ui.row(2 + i, self.top + i == pos, "✓" if self.ticked(row) else " ", row["name"],
                   "" if special or not row.get("bytes") else human(row["bytes"]), note,
                   "green" if self.ticked(row) else "grey", False, switch=True, menu=special)
        current = self.current()
        explain = ""
        if current and current["id"] == "@now":
            explain = ("Ticked: your folders come back in the same run, after the apps and settings. "
                       "Not ticked: the system first, then Restore my files while you work.")
        elif current:
            explain = "  ·  ".join(x for x in (current.get("what"), current.get("why") and
                                    f"Why: {current['why']}", current.get("back") and
                                    f"Without it: {current['back']}") if x)
        job = plan.jobs({"items": [i for p in self.pages for i in p["items"]]}, self.picked)
        ui.bottom(explain, f"Bringing over {plan.summary(job)}", True, KEYS)
        ui.scr.refresh()

    def move(self, delta: int) -> None:
        self.cursor[self.page] = max(0, min(len(self.rows()) - 1, self.cursor.get(self.page, 0) + delta))
        self.ui.say("")

    def turn(self, delta: int) -> None:
        self.page = (self.page + delta) % len(self.pages)
        self.top = 0

    def toggle(self) -> None:
        row = self.current()
        if not row:
            return
        if row["id"] == "@now":
            self.files_now = not self.files_now
        else:
            self.picked ^= {row["id"]}

    def all_or_none(self) -> None:
        ids = {i["id"] for i in self.pages[self.page]["items"]}
        self.picked = self.picked - ids if ids <= self.picked else self.picked | ids

    def run(self) -> dict | None:
        scr = self.ui.scr
        while True:
            self.draw()
            key = scr.getch()
            if key in (curses.KEY_UP, ord("k")):
                self.move(-1)
            elif key in (curses.KEY_DOWN, ord("j")):
                self.move(1)
            elif key in (curses.KEY_RIGHT, ord("l"), 9):
                self.turn(1)
            elif key in (curses.KEY_LEFT, ord("h"), curses.KEY_BTAB):
                self.turn(-1)
            elif key == ord(" "):
                self.toggle()
            elif key == ord("a"):
                self.all_or_none()
            elif key == ord("s"):
                if self.ui.ask("Bring all this over now?"):
                    return {"picked": sorted(self.picked), "files_now": self.files_now}
            elif key in (ord("q"), 27):
                if self.ui.ask("Quit without bringing anything over?"):
                    return None


def run(changes: dict, when: str, picked: set[str] | None = None) -> dict | None:
    os.environ.setdefault("ESCDELAY", "25")
    if not plan.pages(changes):
        return {"picked": [], "files_now": False}
    return curses.wrapper(lambda scr: Chooser(scr, changes, when, picked).run())
