"""Moving one part's files to the backup server (D25).

full():     rsync of the whole part (an old gatekeeper, a boot partition, a
            check of every file's contents): rsync checks every file.
check():    D49 C: a dry run that lists what a full backup would send, with
            sizes, and what it would delete (backup/todo.py keeps the list).
copy():     sends exactly such a list, rsync's log ticking each item off.
everyday(): the improved mix: replay renames/deletes, send changed ranges of
            big files, rsync only the changed files.
copy() and everyday() report an honest bar (backup/meter.py) and stop when
nothing has moved for 3 minutes.
"""

import json
import os
import re
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from omabackups.backup import todo
from omabackups.backup.changes import Plan
from omabackups.backup.meter import Meter
from omabackups.backup.skips import Skips
from omabackups.core import log
from omabackups.core.errors import OmaError
from omabackups.where.server import Gate

BASE = ["-aHAX", "--numeric-ids", "--partial-dir=.rsync-partial"]
_RANGE = struct.Struct(">QQ")
_PROGRESS = re.compile(rb"([\d,]+)B?\s+\d+%")       # rsync --info=progress2: bytes so far
LIVE = ["--info=progress2"]
REPORT_EVERY = 2
OPS_AT_ONCE = 20000


STATS = {"files_checked": "Number of files", "files_sent": "Number of regular files transferred",
         "file_bytes": "Total transferred file size", "wire_bytes": "Total bytes sent"}


class Sender:
    def __init__(self, gate: Gate, backup: str, line: str, compress: bool = False,
                 report=lambda fields: None, stuck_todo: str = ""):
        self.gate, self.backup, self.line = gate, backup, line
        self.stats = {}     # per part: what rsync really sent
        self.compress = compress   # D25: zstd only when away
        self.report = report       # report(fields): the bar's numbers, every few seconds
        self.stuck_todo = stuck_todo or "The next backup carries on from where this one got to."

    def _command(self, part: str, source: str, extra: list[str]) -> list[str]:
        return ["rsync", *BASE, "--stats", *(["-z", "--zc=zstd"] if self.compress else []), *extra,
                "-e", self.gate.rsh(),
                f"--rsync-path=send {self.backup} {self.line} {part}",
                f"{source.rstrip('/')}/", f"{self.gate.rsync_target()}:{part}/"]

    def _rsync(self, part: str, source: str, extra: list[str], meter: Meter | None = None,
               base: int = 0, ticks: Path | None = None) -> bytes:
        """One rsync run. With a meter: the honest bar (bytes so far on top of
        `base`), and a stop when nothing has moved for 3 minutes. Returns its
        output, raw (file names needn't be UTF-8)."""
        command = self._command(part, source, [*extra, *(LIVE if meter else [])])
        log.get("send").debug("rsync %s %s", part, " ".join(extra))
        started = time.monotonic()
        if meter is None:
            done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=self.gate.rsync_env())
            code, out, err, stuck = done.returncode, done.stdout, done.stderr, False
        else:
            code, out, err, stuck = self._live(command, meter, base, ticks)
        text = out.decode("utf-8", "replace")
        # What rsync really did, so a slow backup explains itself.
        found = {key: int(m.group(1).replace(",", "")) for key, label in STATS.items()
                 if (m := re.search(rf"^{label}: ([\d,]+)", text, re.M))}
        found["seconds"] = round(time.monotonic() - started, 1)
        if "-n" not in extra:
            self.stats[part] = {k: self.stats.get(part, {}).get(k, 0) + v for k, v in found.items()}
        log.get("send").info("%s: %s files %s (%s bytes of file data, %s bytes on the wire) "
                             "out of %s checked, in %s s", part, found.get("files_sent", "?"),
                             "to send" if "-n" in extra else "sent",
                             found.get("file_bytes", "?"), found.get("wire_bytes", "?"),
                             found.get("files_checked", "?"), found["seconds"])
        if stuck:
            raise OmaError("Your backup stopped: nothing moved for 3 minutes.", self.stuck_todo,
                           f"{part}: no data sent and no file finished for 3 minutes "
                           f"({meter.sent} of {meter.total} bytes this time)", code="send-stuck")
        if b"No space left on device" in err:          # D50
            from omabackups.backup.check import WONT_FIT_TODO
            raise OmaError(f"Your backup ran out of room while sending {part}: "
                           "this won't fit on your backup location.", WONT_FIT_TODO,
                           err.decode("utf-8", "replace").strip()[-2000:], code="backup-full")
        # 24: some files vanished while being sent (normal for a live /boot).
        if code not in (0, 24):
            raise OmaError(f"Sending the {part} part of your backup stopped.",
                           "The next backup picks up where this one stopped.",
                           err.decode("utf-8", "replace").strip()[-2000:] or f"rsync exit {code}",
                           code="send-failed")
        return out

    def _live(self, command: list[str], meter: Meter, base: int, ticks: Path | None):
        """rsync with its progress read as it goes; stopped if stuck."""
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, env=self.gate.rsync_env())
            seen, tail = {"sent": 0}, bytearray()

            def read():
                window = b""
                while chunk := proc.stdout.read1(1 << 16):
                    tail.extend(chunk)
                    del tail[:-65536]                     # the stats come at the end
                    window = (window + chunk)[-4096:]
                    if found := _PROGRESS.findall(window):
                        seen["sent"] = int(found[-1].replace(b",", b""))
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            stuck, reported = False, 0.0
            while proc.poll() is None:
                time.sleep(0.5)
                grown = ticks.stat().st_size if ticks and ticks.exists() else None
                meter.update(sent=base + seen["sent"], ticks=grown)
                if time.monotonic() - reported >= REPORT_EVERY:
                    self.report(meter.snapshot())
                    reported = time.monotonic()
                if meter.stuck():
                    stuck = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break
            reader.join(timeout=20)
            code = proc.wait()
            meter.update(sent=base + seen["sent"])
            err.seek(0)
            return code, bytes(tail), err.read(), stuck

    def check(self, part: str, source: str, skips: Skips) -> tuple[list, list, int]:
        """D49 C: what a full backup of `source` would send and delete, and the
        part's whole size. Once."""
        from omabackups.backup.full import total_size
        out = self._rsync(part, source, ["-n", "-8", f"--out-format={todo.OUT_FORMAT}",
                                         "--delete", "--delete-excluded", *skips.rsync_rules()])
        items, deletes = todo.parse_check(out)
        return items, deletes, total_size(out)

    def remove(self, part: str, ops: list) -> None:
        """Deletes (and renames) on the server before a copy, in batches."""
        for at in range(0, len(ops), OPS_AT_ONCE):
            self.gate.call("apply", self.backup, self.line, part,
                           data=json.dumps(ops[at:at + OPS_AT_ONCE]).encode())

    def copy(self, part: str, source: str, items: list[tuple[str, int]], already: int = 0) -> None:
        """Exactly the to-do list, each item ticked off in todo's log as it goes."""
        meter = Meter(sum(size for _, size in items), already)
        self.report(meter.snapshot())
        if not items:
            return
        log_file = todo.folder(part) / "done.log"
        with tempfile.NamedTemporaryFile("wb", prefix="omabackups-todo-") as listing:
            listing.write(b"\0".join(p.encode("utf-8", "surrogateescape") for p, _ in items) + b"\0")
            listing.flush()
            self._rsync(part, source, [f"--files-from={listing.name}", "--from0",
                                       f"--log-file={log_file}", f"--log-file-format={todo.LOG_FORMAT}"],
                        meter, ticks=log_file)
        meter.update(sent=meter.total)
        self.report({**meter.snapshot(), "percent": 100})

    def resend(self, part: str, source: str, paths: list[str]) -> None:
        """Damaged files again, by name, whole (-I: even though size and date
        still match; -W: no deltas against the damaged copy). Audit 4.2."""
        with tempfile.NamedTemporaryFile("wb", prefix="omabackups-damaged-") as listing:
            listing.write(b"\0".join(p.encode("utf-8", "surrogateescape") for p in paths) + b"\0")
            listing.flush()
            self._rsync(part, source, [f"--files-from={listing.name}", "--from0", "-I", "-W"])

    def full(self, part: str, source: str, skips: Skips, checksum: bool = False) -> None:
        """checksum: compare every file's contents, not just size and date
        (after the health check found damaged files: they're sent again)."""
        self._rsync(part, source, ["--delete", "--delete-excluded", *(["-c"] if checksum else []),
                                   *skips.rsync_rules()])

    def everyday(self, part: str, snapshot: str, plan: Plan, total: int = 0) -> None:
        meter = Meter(total)
        self.report(meter.snapshot())
        if plan.ops:
            self.gate.call("apply", self.backup, self.line, part, data=json.dumps(plan.ops).encode())
        for path, spans in plan.ranges.items():
            self._ranges(part, snapshot, path, spans, meter)
        if plan.files:
            with tempfile.NamedTemporaryFile("wb", prefix="omabackups-files-") as listing:
                listing.write(b"\0".join(p.encode("utf-8", "surrogateescape") for p in plan.files) + b"\0")
                listing.flush()
                self._rsync(part, snapshot, [f"--files-from={listing.name}", "--from0"], meter, base=meter.sent)
        meter.update(sent=meter.total)
        self.report({**meter.snapshot(), "percent": 100})

    def _ranges(self, part: str, snapshot: str, path: str, spans: list, meter: Meter | None = None) -> None:
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
                        if meter:
                            meter.update(sent=meter.sent + len(chunk))

        self.gate.call_streaming("ranges", self.backup, self.line, part, feed=feed)

