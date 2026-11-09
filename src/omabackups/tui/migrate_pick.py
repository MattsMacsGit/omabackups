"""Choose what comes over (6.1 F step 3, D14, 7.2), drawn the way 1.x's
Migrate picker was (lesson, stage 8): numbered tabs across the top, each
marked once looked at; a line saying what's still to look at; the keys
spelled out; and starting only once every page has been seen. Enter only
moves to the next page; S starts (as Save in the file chooser), so nobody
starts it by accident (D41).

Pages: Settings & logins first (what matters most), then Apps, Keybindings,
bar & theme, System tweaks, Backgrounds, Your files (its first row: now or
later). Suggestions start ticked; the lines under the list explain the
highlighted one.
"""

import curses
import os

from omabackups.backup.check import human
from omabackups.migrate import plan
from omabackups.tui import kit

ORDER = ("settings", "apps", "desktop", "tweaks", "backgrounds", "files")
TITLES = {"settings": "Settings & logins"}
SUGGEST = {"keep": "Keep", "you": "Up to you", "leave": "Leave"}
NOW_ROW = {"id": "@now", "name": "Bring them back now, in the same run (start it and walk away)"}
KEYS = (("↑↓", "move"), ("Space", "tick"), ("←→ or 1-9", "pages"), ("a", "all/none"),
        ("Enter", "next page"), ("s", "start"), ("q", "quit"))


def ordered(changes: dict) -> list[dict]:
    pages = {p["id"]: p for p in plan.pages(changes)}
    out = [pages[g] for g in ORDER if g in pages] + [p for g, p in pages.items() if g not in ORDER]
    for p in out:
        p["title"] = TITLES.get(p["id"], p["title"])
    return out


class Chooser:
    def __init__(self, scr, changes: dict, when: str, picked: set[str] | None = None, preview: bool = False):
        self.ui = kit.Screen(scr)
        self.pages = ordered(changes)
        self.picked = set(plan.suggested(changes) if picked is None else picked)
        self.files_now, self.preview = True, preview
        self.when, self.page, self.cursor, self.top = when, 0, {}, 0
        self.seen = {0}

    def rows(self, page: int | None = None) -> list[dict]:
        p = self.pages[self.page if page is None else page]
        return ([NOW_ROW] if p["id"] == "files" else []) + p["items"]

    def current(self) -> dict | None:
        rows = self.rows()
        return rows[min(self.cursor.get(self.page, 0), len(rows) - 1)] if rows else None

    def ticked(self, row: dict) -> bool:
        return self.files_now if row["id"] == "@now" else row["id"] in self.picked

    def unseen(self) -> list[str]:
        return [p["title"] for n, p in enumerate(self.pages) if n not in self.seen]

    # --- drawing ---------------------------------------------------------------------

    def draw_tabs(self) -> None:
        ui, x = self.ui, 1
        for n, p in enumerate(self.pages):
            mine = [i for i in p["items"]]
            label = f" {n + 1} {p['title']} ({sum(i['id'] in self.picked for i in mine)}/{len(mine)}) "
            attr = curses.A_REVERSE | curses.A_BOLD if n == self.page else 0
            x = ui.put(2, x, label, attr)
            done = n in self.seen
            x = ui.put(2, x, "✓" if done else "○", ui.col(kit.GREEN if done else kit.YELLOW, curses.A_BOLD)) + 2
        _, w = ui.size()
        ui.put(3, 0, "─" * (w - 1), ui.col(kit.GREY))

    def draw_keys(self) -> None:
        ui = self.ui
        h, _ = ui.size()
        ui.put(h - 1, 0, " " * (ui.size()[1] - 1))
        x = 2
        for key, what in KEYS:
            x = ui.put(h - 1, x, key, ui.col(kit.ACCENT, curses.A_BOLD))
            x = ui.put(h - 1, x + 1, what, ui.col(kit.GREY)) + 3

    def draw(self) -> None:
        ui = self.ui
        ui.scr.erase()
        h, w = ui.size()
        if h < 16 or w < 70:
            ui.put(0, 0, "Make this window bigger (at least 70 x 16).", ui.col(kit.YELLOW))
            ui.scr.refresh()
            return
        title = "Choose what comes over" + ("  ·  PREVIEW, nothing changes" if self.preview else "")
        ui.put(0, 1, title, ui.col(kit.ACCENT, curses.A_BOLD))
        right = f"Here's what you had as of {self.when}"
        ui.put(0, max(len(title) + 4, w - len(right) - 2), right, curses.A_BOLD)
        self.draw_tabs()
        rows, top_y = self.rows(), 4
        height = max(1, h - top_y - kit.Screen.BOTTOM)
        pos = min(self.cursor.get(self.page, 0), max(0, len(rows) - 1))
        self.top = min(self.top, pos) if pos < self.top else max(self.top, pos - height + 1)
        for i, row in enumerate(rows[self.top:self.top + height]):
            special = row["id"] == "@now"
            ui.row(top_y + i, self.top + i == pos, "✓" if self.ticked(row) else " ", row["name"],
                   "" if special or not row.get("bytes") else human(row["bytes"]),
                   "" if special else SUGGEST.get(row.get("suggest"), ""),
                   "green" if self.ticked(row) else "grey", False, switch=True, menu=special)
        current = self.current()
        if current and current["id"] == "@now":
            explain = ("Ticked: your folders come back in the same run, after the apps and settings. "
                       "Not ticked: the system first, then Restore my files while you work.")
        else:
            explain = "  ·  ".join(x for x in (current and current.get("what"),
                                               current and current.get("why") and f"Why: {current['why']}",
                                               current and current.get("back") and f"Without it: {current['back']}") if x)
        job = plan.jobs({"items": [i for p in self.pages for i in p["items"]]}, self.picked)
        todo = self.unseen()
        status = f"Bringing over {plan.summary(job)}"
        note = ("Still to look at: " + ", ".join(todo)) if todo else "Every page looked at: press S to start"
        ui.bottom(explain, status, True, "", note)
        if not todo and not ui.message:
            ui.put(h - 3, 2, note, ui.col(kit.GREEN, curses.A_BOLD))
        self.draw_keys()
        ui.scr.refresh()

    # --- keys -------------------------------------------------------------------------

    def go(self, page: int) -> None:
        self.page = page % len(self.pages)
        self.seen.add(self.page)
        self.top = 0
        self.ui.say("")

    def move(self, delta: int) -> None:
        self.cursor[self.page] = max(0, min(len(self.rows()) - 1, self.cursor.get(self.page, 0) + delta))
        self.ui.say("")

    def toggle(self) -> None:
        row = self.current()
        if row and row["id"] == "@now":
            self.files_now = not self.files_now
        elif row:
            self.picked ^= {row["id"]}

    def all_or_none(self) -> None:
        ids = {i["id"] for i in self.pages[self.page]["items"]}
        self.picked = self.picked - ids if ids <= self.picked else self.picked | ids

    def enter(self) -> None:
        """Enter: the next page still to look at, or simply the next page."""
        todo = [n for n in range(len(self.pages)) if n not in self.seen]
        self.go(next((n for n in todo if n > self.page), todo[0]) if todo else self.page + 1)

    def start(self) -> dict | None:
        """S: start, once every page has been looked at (1.x)."""
        todo = [n for n in range(len(self.pages)) if n not in self.seen]
        if todo:
            self.go(next((n for n in todo if n > self.page), todo[0]))
            self.ui.say("Look at every page first: this is the next one. Then press S.")
            return None
        question = "Show what Migrate would do?" if self.preview else "Bring all this over now?"
        if self.ui.ask(question):
            return {"picked": sorted(self.picked), "files_now": self.files_now}
        return None

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
                self.go(self.page + 1)
            elif key in (curses.KEY_LEFT, ord("h"), curses.KEY_BTAB):
                self.go(self.page - 1)
            elif ord("1") <= key <= ord("9") and key - ord("1") < len(self.pages):
                self.go(key - ord("1"))
            elif key == ord(" "):
                self.toggle()
            elif key == ord("a"):
                self.all_or_none()
            elif key in (curses.KEY_ENTER, 10, 13):
                self.enter()
            elif key in (ord("s"), ord("S")):
                chosen = self.start()
                if chosen is not None:
                    return chosen
            elif key in (ord("q"), 27):
                if self.ui.ask("Quit without bringing anything over?"):
                    return None


def run(changes: dict, when: str, picked: set[str] | None = None, preview: bool = False) -> dict | None:
    os.environ.setdefault("ESCDELAY", "25")
    if not plan.pages(changes):
        return {"picked": [], "files_now": False}
    return curses.wrapper(lambda scr: Chooser(scr, changes, when, picked, preview).run())
