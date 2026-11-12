"""How far one part's copy has got, honestly (D49).

The total is known before the copy starts (the check's to-do list, or the
everyday plan), so the bar is sent / total. On top of it:
- speed: what moved over the last minute;
- time left: only once a few minutes of steady sending have passed, from
  the average over the last minutes, rounded; never a guess off the first
  seconds (skipped and tiny files make early speeds meaningless);
- stuck: nothing moved (no bytes, no file finished) for STUCK seconds.

The clock is time.monotonic, which stops while the computer sleeps: a
laptop asleep for an hour hasn't been "stuck" for an hour.
"""

import time
from collections import deque

STUCK = 180              # D49: nothing moved for 3 minutes
SPEED_WINDOW = 60        # "the current speed"
LEFT_WINDOW = 300        # time left from the last 5 minutes
LEFT_AFTER = 180         # ...and only after 3 minutes of sending


class Meter:
    def __init__(self, total: int, already: int = 0, clock=time.monotonic):
        self.total, self.already, self.clock = max(0, total), max(0, already), clock
        self.sent = 0
        self.started = self.moved = clock()
        self.samples = deque([(self.started, 0)])
        self.ticks = 0

    def update(self, sent: int | None = None, ticks: int | None = None) -> None:
        """sent: bytes so far this copy (never goes back); ticks: files finished."""
        now = self.clock()
        moved = False
        if sent is not None and sent > self.sent:
            self.sent, moved = sent, True
        if ticks is not None and ticks > self.ticks:
            self.ticks, moved = ticks, True
        if moved:
            self.moved = now
        if self.total and self.sent > self.total:      # something grew since the check
            self.total = self.sent
        self.samples.append((now, self.sent))
        while len(self.samples) > 2 and now - self.samples[1][0] > LEFT_WINDOW:
            self.samples.popleft()

    def _rate(self, window: float) -> float:
        now = self.clock()
        old = next(((t, s) for t, s in self.samples if now - t <= window), self.samples[-1])
        span = now - old[0]
        return (self.sent - old[1]) / span if span > 0 else 0.0

    def speed(self) -> float:
        return self._rate(SPEED_WINDOW)

    def left(self) -> int | None:
        if self.clock() - self.started < LEFT_AFTER or not self.total:
            return None
        rate = self._rate(LEFT_WINDOW)
        if rate <= 0:
            return None
        return int((self.total - self.sent) / rate)

    def stuck(self) -> bool:
        return self.clock() - self.moved >= STUCK

    def fraction(self) -> float:
        if not self.total:
            return 0.0
        return min(0.99, self.sent / self.total)      # 100% only when rsync has finished

    def snapshot(self) -> dict:
        return {"sent": self.sent, "total": self.total, "already": self.already,
                "speed": int(self.speed()), "left": self.left(),
                "percent": int(100 * self.fraction()), "quiet": int(self.clock() - self.moved)}


def rounded(seconds: int | None) -> str:
    """'about 3 h 20 min', 'about 25 min', 'less than a minute'; '' if unknown."""
    if seconds is None:
        return ""
    if seconds < 60:
        return "less than a minute"
    minutes = seconds / 60
    if minutes < 10:
        return f"about {round(minutes)} min"
    if minutes < 60:
        return f"about {int(round(minutes / 5) * 5)} min"
    step = 10 if minutes >= 120 else 5
    whole = int(round(minutes / step) * step)
    h, m = divmod(whole, 60)
    return f"about {h} h" + (f" {m} min" if m else "")


def size(n: int | float) -> str:
    """Bytes in words: '12.4 GB', '850 MB'."""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") or n >= 100 else f"{n:.1f} {unit}"
        n /= 1000
    return ""
