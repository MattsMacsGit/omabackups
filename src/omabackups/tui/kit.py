"""The shared terminal look (BUILD 5.6, 7.0): one screen at a time, the keys
always on screen, colours from the terminal (which Omarchy's theme sets, so
they follow the live theme). Status colours mean the same everywhere:
green = done/safe, blue = will happen, grey = skipped/off, yellow = a
warning, red = a real problem (only its one-line title).
"""

import curses

GREEN, BLUE, GREY, YELLOW, RED, ACCENT = 1, 2, 3, 4, 5, 6
COLOURS = {"green": GREEN, "blue": BLUE, "grey": GREY, "yellow": YELLOW, "red": RED}


class Screen:
    def __init__(self, scr):
        self.scr = scr
        curses.curs_set(0)
        scr.keypad(True)
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            grey = 8 if curses.COLORS >= 16 else curses.COLOR_WHITE
            for pair, colour in ((GREEN, curses.COLOR_GREEN), (BLUE, curses.COLOR_BLUE), (GREY, grey),
                                 (YELLOW, curses.COLOR_YELLOW), (RED, curses.COLOR_RED),
                                 (ACCENT, curses.COLOR_MAGENTA)):
                curses.init_pair(pair, colour, -1)
        self.message, self.message_colour = "", YELLOW

    def size(self) -> tuple[int, int]:
        return self.scr.getmaxyx()

    def col(self, pair: int, extra: int = 0) -> int:
        return (curses.color_pair(pair) if curses.has_colors() else 0) | extra

    def put(self, y: int, x: int, text: str, attr: int = 0) -> int:
        h, w = self.size()
        if y < 0 or y >= h or x >= w - 1:
            return x
        text = text[: max(0, w - 1 - x)]
        try:
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass
        return x + len(text)

    def header(self, title: str, where: str) -> None:
        h, w = self.size()
        self.put(0, 1, title, self.col(ACCENT, curses.A_BOLD))
        self.put(0, max(len(title) + 3, w - len(where) - 2), where, curses.A_BOLD)
        self.put(1, 0, "─" * (w - 1), self.col(GREY))

    def row(self, y: int, selected: bool, mark: str, name: str, size: str, note: str, colour: str,
            opens: bool, switch: bool = False, menu: bool = False) -> None:
        """One line of a list. A switch (not a file) shows its mark in a box;
        a menu row (a page of switches, not a folder) shows in the accent colour."""
        h, w = self.size()
        base = curses.A_REVERSE if selected else 0
        tint = self.col(ACCENT if menu else COLOURS.get(colour, GREY))
        self.put(y, 0, " " * (w - 1), base)
        x = self.put(y, 1, ("▸ " if selected else "  "), base | curses.A_BOLD)
        if menu:
            x = self.put(y, x, "☰  ", tint | base | curses.A_BOLD)
        else:
            x = self.put(y, x, f"[{mark}] " if switch else f"{mark}   ", tint | base | curses.A_BOLD)
        name_width = max(10, w - 34)
        self.put(y, x, name[:name_width], tint | base | (curses.A_BOLD if menu else 0))
        self.put(y, x + name_width + 1, size.rjust(9), tint | base)
        self.put(y, x + name_width + 12, note, self.col(GREY) | base)
        if opens:
            self.put(y, w - 3, "›", base)

    # The bottom of the screen: a rule, the highlighted row's explainer (two
    # lines, wrapped, so a long one isn't cut off), a message or the standing
    # note, the total, and the keys.
    BOTTOM = 6

    def bottom(self, explain: str, total: str, fits: bool, keys: str, note: str = "") -> None:
        import textwrap
        h, w = self.size()
        self.put(h - 6, 0, "─" * (w - 1), self.col(GREY))
        lines = textwrap.wrap(explain, max(10, w - 5)) or [""]
        if len(lines) > 2:
            lines = [lines[0], textwrap.shorten(" ".join(lines[1:]), max(10, w - 5), placeholder="…")]
        for n, line in enumerate(lines):
            self.put(h - 5 + n, 2, line)
        if self.message:
            self.put(h - 3, 2, self.message, self.col(self.message_colour, curses.A_BOLD))
        elif note:
            self.put(h - 3, 2, note, self.col(BLUE, curses.A_BOLD))
        self.put(h - 2, 2, total, self.col(RED, curses.A_BOLD) if not fits else curses.A_BOLD)
        self.put(h - 1, 2, keys, self.col(GREY))

    def say(self, text: str, colour: int = YELLOW) -> None:
        self.message, self.message_colour = text, colour

    def ask(self, question: str) -> bool:
        """A yes/no question on the message line; y or n (Esc = no)."""
        h, w = self.size()
        self.put(h - 3, 0, " " * (w - 1))
        self.put(h - 3, 2, question + " (y/n)", self.col(YELLOW, curses.A_BOLD))
        self.scr.refresh()
        self.scr.timeout(-1)
        while True:
            key = self.scr.getch()
            if key in (ord("y"), ord("Y")):
                return True
            if key in (ord("n"), ord("N"), 27):      # Esc = no
                return False
            # (any other key: still waiting for y or n)
