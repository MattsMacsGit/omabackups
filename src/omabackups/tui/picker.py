"""THE picker, "Choose what gets backed up" (D12, D13; screens agreed 7 Nov).

`omabackups pick` opens it in the terminal (the panel opens a terminal for
it). ↑↓ move, Enter open, ⌫ back, Space tick, s save & quit, q quit.
Sizes are measured in the background, so the screen never waits.
"""

import curses
import json
import threading
import time

from omabackups.backup.check import human
from omabackups.core import paths, rootjob
from omabackups.core.errors import OmaError
from omabackups.tui import kit
from omabackups.tui.pick_model import Model

KEYS = "↑↓ move  Enter open  ⌫/Esc back  Space tick  h hidden  s save  q quit"
FIRST_KEYS = "↑↓ move  Enter open  ⌫/Esc back  Space tick  h hidden  s save & start backup  q quit"
FIRST_NOTE = "Make your choices, then press s to save: your first backup starts straight away."
TITLE = "Choose what gets backed up"


class Picker:
    def __init__(self, scr, model: Model, first: bool = False):
        self.ui, self.model, self.first = kit.Screen(scr), model, first
        self.stack, self.cursor, self.top = [model.home()], {model.home(): 0}, 0
        self.rows, self.running, self.saved = [], True, False
        threading.Thread(target=self._measure, daemon=True).start()

    # --- background sizes -------------------------------------------------------

    def _measure(self) -> None:
        while self.running:
            for node in (self.stack[-1], self.model.home(), self.model.quick(), self.model.system()):
                if self.running and self.model.size(node) is None:
                    self.model.measure(node, stop=lambda: not self.running)
            time.sleep(0.3)

    # --- drawing ---------------------------------------------------------------

    def where(self) -> str:
        names = [n.name for n in self.stack]
        return " › ".join(names)

    def draw(self) -> None:
        ui, m = self.ui, self.model
        ui.scr.erase()
        h, w = ui.size()
        node = self.stack[-1]
        self.rows = m.listing(node)
        ui.header(TITLE, self.where())
        height = max(1, h - 2 - kit.Screen.BOTTOM)
        pos = min(self.cursor.get(node, 0), max(0, len(self.rows) - 1))
        self.cursor[node] = pos
        if pos < self.top:
            self.top = pos
        elif pos >= self.top + height:
            self.top = pos - height + 1
        for i, child in enumerate(self.rows[self.top:self.top + height]):
            size = m.size(child)
            skipped = m.skipped(child)
            note = ("in older restore points" if m.colour(child) == "yellow" else "skipped") \
                if skipped and child.rel else ""
            inside = m.inside_skipped(child)
            if not skipped and inside:
                note = f"{inside} thing{'s' if inside > 1 else ''} skipped"
            menu = child == m.quick()                 # a page of switches, not a folder
            if menu:
                note, size = "switches for big things", None
            show = (not skipped or child.part == "quick") and not menu   # a switch shows what it saves
            ui.row(2 + i, self.top + i == pos, m.mark(child), child.name,
                   "" if not show else (human(size) if size else "…" if size is None else "0 bytes"),
                   note, m.colour(child), child.is_dir, switch=child.part == "quick" and not menu,
                   menu=menu)
        if not self.rows:
            ui.put(3, 4, "(empty, or can't be read)", ui.col(kit.GREY))
        current = self.rows[pos] if self.rows else None
        text, fits = m.bottom()
        ui.bottom(m.explain(current) if current else "", text, fits,
                  FIRST_KEYS if self.first else KEYS, FIRST_NOTE if self.first else "")
        ui.scr.refresh()

    # --- keys --------------------------------------------------------------------

    def move(self, delta: int) -> None:
        node = self.stack[-1]
        self.cursor[node] = max(0, min(len(self.rows) - 1, self.cursor.get(node, 0) + delta))
        self.ui.say("")

    def current(self):
        node = self.stack[-1]
        return self.rows[self.cursor.get(node, 0)] if self.rows else None

    def open(self) -> None:
        child = self.current()
        if child and child.is_dir:            # skipped ones too: look before you choose
            self.stack.append(child)
            self.cursor.setdefault(child, 0)
            self.top = 0

    def back(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()
            self.top = 0

    def save(self) -> bool:
        try:
            rootjob.run("set-skips", {"skips": self.model.to_save()})
        except OmaError as exc:
            self.ui.say(f"Not saved: {exc.what}", kit.RED)
            return False
        self.saved = True       # (the root job paused automatic backups: D29)
        return True

    def run(self) -> bool:
        scr = self.ui.scr
        while True:
            self.draw()
            scr.timeout(300)
            key = scr.getch()
            if key in (curses.KEY_UP, ord("k")):
                self.move(-1)
            elif key in (curses.KEY_DOWN, ord("j")):
                self.move(1)
            elif key == curses.KEY_PPAGE:
                self.move(-10)
            elif key == curses.KEY_NPAGE:
                self.move(10)
            elif key in (curses.KEY_ENTER, 10, 13, curses.KEY_RIGHT):
                self.open()
            elif key in (curses.KEY_BACKSPACE, 127, 8, curses.KEY_LEFT, 27):   # Esc goes back too
                self.back()
            elif key == ord(" "):
                child = self.current()
                problem = self.model.toggle(child) if child else None
                self.ui.say(problem or "")
            elif key in (ord("h"), ord("H")):
                self.model.show_hidden = not self.model.show_hidden
                self.ui.say("Showing hidden files too." if self.model.show_hidden
                            else "Hidden files aren't shown (they're still backed up).")
            elif key == ord("s"):
                # Always asked first: easy to hit by accident.
                question = "Save and start your first backup?" if self.first else "Save your changes and quit?"
                if self.ui.ask(question) and self.save():
                    break
            elif key == ord("q"):
                if self.ui.ask("Quit without saving your changes?" if self.model.dirty else "Quit?"):
                    break
            elif key == curses.KEY_MOUSE:
                self.mouse()
        self.running = False
        return self.saved

    def mouse(self) -> None:
        try:
            _, _, y, _, state = curses.getmouse()
        except curses.error:
            return
        index = self.top + y - 2
        if 0 <= index < len(self.rows):
            self.cursor[self.stack[-1]] = index
            if state & (curses.BUTTON1_DOUBLE_CLICKED):
                self.open()


def load_record() -> dict:
    try:
        return json.loads((paths.system_state_dir() / "backup.json").read_text())
    except (OSError, ValueError):
        return {}


def run(user: str, first: bool = False) -> bool:
    """The picker; `first`: saving starts the first backup, and it says so."""
    import os
    os.environ.setdefault("ESCDELAY", "25")   # Esc means "back" at once, not after a second
    from pathlib import Path
    roots = None
    if os.environ.get("OMABACKUPS_SYSROOT"):      # tests: the sandbox's home and system
        roots = {"home": Path.home().parent, "system": Path(os.environ["OMABACKUPS_SYSROOT"])}
        user = Path.home().name
    model = Model(user, load_record(), roots=roots)
    return curses.wrapper(lambda scr: Picker(scr, model, first).run())
