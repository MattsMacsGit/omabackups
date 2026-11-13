"""Keeping the backup unlocked while a long job runs (1.x lesson)."""

import threading

from omabackups.core.errors import OmaError


class HoldKeeper:
    """Says "still here" to the server every 2 minutes for the whole backup. A
    hold nobody refreshes for 10 minutes counts as abandoned (1.x lesson: long
    jobs say so as they go); one slow part once outlasted it (stage 3 test)."""

    EVERY = 120

    def __init__(self, gate, bid: str, hold: str, logger):
        self.gate, self.bid, self.hold, self.logger = gate, bid, hold, logger
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.done.wait(self.EVERY):
            try:
                self.gate.call("hold", self.bid, self.hold)
            except OmaError as exc:
                self.logger.warning("keeping the hold: %s", exc.details)

    def stop(self) -> None:
        self.done.set()
        self.thread.join(timeout=5)
