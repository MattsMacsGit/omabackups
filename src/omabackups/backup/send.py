"""Moving one part's files to the backup server (D25).

full():     rsync of the whole part (the first backup, and after any trouble):
            rsync checks every file, so it always ends with an exact copy.
everyday(): the improved mix: replay renames/deletes, send changed ranges of
            big files, rsync only the changed files.
"""

import json
import struct
import subprocess
import tempfile
from pathlib import Path

from omabackups.backup.changes import Plan
from omabackups.backup.skips import Skips
from omabackups.core import log
from omabackups.core.errors import OmaError
from omabackups.where.server import Gate

BASE = ["-aHAX", "--numeric-ids", "--partial-dir=.rsync-partial"]
_RANGE = struct.Struct(">QQ")


class Sender:
    def __init__(self, gate: Gate, backup: str, line: str, compress: bool = False):
        self.gate, self.backup, self.line = gate, backup, line
        self.compress = compress   # D25: zstd only when away

    def _rsync(self, part: str, source: str, extra: list[str]) -> None:
        command = ["rsync", *BASE, *(["-z", "--zc=zstd"] if self.compress else []), *extra,
                   "-e", self.gate.rsh(),
                   f"--rsync-path=send {self.backup} {self.line} {part}",
                   f"{source.rstrip('/')}/", f"{self.gate.rsync_target()}:{part}/"]
        log.get("send").debug("rsync %s %s", part, " ".join(extra))
        done = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                              env=self.gate.rsync_env())
        # 24: some files vanished while being sent (normal for a live /boot).
        if done.returncode not in (0, 24):
            raise OmaError(f"Sending the {part} part of your backup stopped.",
                           "The next backup picks up where this one stopped.",
                           done.stderr.strip()[-2000:] or f"rsync exit {done.returncode}",
                           code="send-failed")

    def full(self, part: str, source: str, skips: Skips, checksum: bool = False) -> None:
        """checksum: compare every file's contents, not just size and date
        (after the health check found damaged files: they're sent again)."""
        self._rsync(part, source, ["--delete", "--delete-excluded", *(["-c"] if checksum else []),
                                   *skips.rsync_rules()])

    def everyday(self, part: str, snapshot: str, plan: Plan) -> None:
        if plan.ops:
            self.gate.call("apply", self.backup, self.line, part, data=json.dumps(plan.ops).encode())
        for path, spans in plan.ranges.items():
            self._ranges(part, snapshot, path, spans)
        if plan.files:
            with tempfile.NamedTemporaryFile("wb", prefix="omabackups-files-") as listing:
                listing.write(b"\0".join(p.encode("utf-8", "surrogateescape") for p in plan.files) + b"\0")
                listing.flush()
                self._rsync(part, snapshot, [f"--files-from={listing.name}", "--from0"])

    def _ranges(self, part: str, snapshot: str, path: str, spans: list) -> None:
        full = Path(snapshot) / path
        info = full.stat()
        head = {"path": path, "size": info.st_size, "mode": info.st_mode, "uid": info.st_uid,
                "gid": info.st_gid, "mtime_ns": info.st_mtime_ns}

        def feed(pipe):
            pipe.write(json.dumps(head).encode() + b"\n")
            with open(full, "rb") as f:
                for offset, length in spans:
                    length = max(0, min(length, info.st_size - offset))
                    pipe.write(_RANGE.pack(offset, length))
                    f.seek(offset)
                    while length:
                        chunk = f.read(min(length, 1 << 20))
                        if not chunk:
                            raise OmaError(f"{path} got shorter while it was being sent.",
                                           "The next backup sends it again.", code="send-failed")
                        pipe.write(chunk)
                        length -= len(chunk)

        self.gate.call_streaming("ranges", self.backup, self.line, part, feed=feed)

