"""One backup's state, handed from step to step (backup/run.py)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from omabackups.backup import reuse
from omabackups.backup.send import Sender
from omabackups.where.server import Gate


@dataclass
class Job:
    """One backup, handed from step to step."""
    gate: Gate
    server: dict
    away: bool
    gate_version: int
    record: dict
    progress: Callable
    logger: Any
    verdict: dict = field(default_factory=dict)
    resend: bool = False          # damaged files go again, all of them
    hold: str = ""
    sender: Sender | None = None
    settings: dict = field(default_factory=dict)
    run: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%dT%H%M%S"))
    since: dict = field(default_factory=dict)       # each part's "since" snapshot
    made: dict = field(default_factory=dict)        # this run's snapshots
    opened: dict = field(default_factory=dict)      # each part's snapshots
    work: list = field(default_factory=list)        # (part, skip, snapshot, plan)
    how: dict = field(default_factory=dict)
    fingerprints: dict = field(default_factory=dict)
    manifests: dict = field(default_factory=dict)
    left_out: list = field(default_factory=list)
    needed: int = 0
    known: bool = True            # the size is known (else the room isn't checked)
    forced_past: str = ""         # a forced backup after a partial restore: its point

    @property
    def bid(self) -> str:
        return self.server["backup"]

    @property
    def line(self) -> str:
        return self.server.get("line", "001")

    @property
    def reusing(self) -> bool:
        return self.gate_version >= reuse.NEEDS_GATE
