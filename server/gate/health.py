"""Is your backup still holding what was written to it? (D18, 1.x's check, kept)

btrfs keeps a checksum of every block; a scrub reads everything back and
checks it. On a Pi that takes hours, so it's done a slice a night: each
night carries on where the last stopped. The verdict (1.x's rules):
  healthy   nothing wrong found
  warning   the disk reported read or write errors, but no damaged file
  damaged   files no longer match what was written
  unknown   never checked
Damage found stands until a full pass reads everything again.
"""

import json
import re
import subprocess
import tempfile
import time

import conf
from registry import _write_atomic

ERRORS = ("csum_errors", "read_errors", "verify_errors", "super_errors",
          "uncorrectable_errors", "corrected_errors")
DEVICE = ("write_io_errs", "read_io_errs", "flush_io_errs", "corruption_errs", "generation_errs")
MAX_FILES = 200
PATH_RE = re.compile(r"\broot (?P<root>\d+),.*\(path: (?P<path>.*)\)\s*$")


def state_file(bid: str):
    return conf.REGISTRY.parent / "health" / f"{bid}.json"


def load(bid: str) -> dict:
    try:
        return json.loads(state_file(bid).read_text())
    except (OSError, ValueError):
        return {}


def save(bid: str, record: dict) -> None:
    state_file(bid).parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(state_file(bid), json.dumps(record, indent=2) + "\n", 0o600)


# --- the disk (real btrfs; a pretend scrub in test mode) ---------------------

def _fake(bid: str) -> dict:
    try:
        return json.loads((conf.RUN / f"fake-scrub-{bid}.json").read_text())
    except (OSError, ValueError):
        return {"status": "none"}


def scrub(verb: str, mount: str, bid: str) -> tuple[int, str]:
    """start | resume | cancel. Start/resume fork into the background and keep
    their output open until the scrub ends: never pipes (1.x lesson)."""
    if conf.TEST:
        state = _fake(bid)
        state["status"] = "running" if verb in ("start", "resume") else "interrupted"
        (conf.RUN / f"fake-scrub-{bid}.json").write_text(json.dumps(state))
        return 0, ""
    if verb == "cancel":
        done = subprocess.run(["btrfs", "scrub", "cancel", mount], capture_output=True, text=True)
        return done.returncode, done.stderr
    # Each request runs as its own short service, and systemd stops whatever a
    # service leaves behind when it ends: a scrub started from here directly
    # was cancelled seconds later (stage 3 test). So it runs as a service of
    # its own, in the foreground (-B) there; cancel stops it the usual way.
    with tempfile.TemporaryFile(mode="w+") as err:
        done = subprocess.run(
            ["systemd-run", f"--unit=omabackups-gate-scrub-{bid[:12]}", "--collect", "--quiet",
             "-p", "Nice=10", "btrfs", "scrub", verb, "-B", "-c", "3", mount],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err, text=True)
        err.seek(0)
        return done.returncode, err.read()


def scrub_status(mount: str, bid: str) -> dict:
    if conf.TEST:
        return _fake(bid)
    done = subprocess.run(["btrfs", "scrub", "status", "-R", mount], capture_output=True, text=True)
    out: dict = {"status": "none"}
    for line in done.stdout.splitlines():
        key, _, value = line.strip().partition(":")
        value = value.strip()
        if key == "Status":
            out["status"] = value.split()[0] if value else "none"
        elif key in ERRORS or key in ("data_bytes_scrubbed", "tree_bytes_scrubbed"):
            try:
                out[key] = int(value)
            except ValueError:
                pass
    if "no stats available" in done.stdout:
        out["status"] = "none"
    return out


def device_stats(mount: str) -> dict:
    out = {k: 0 for k in DEVICE}
    if conf.TEST:
        return out
    done = subprocess.run(["btrfs", "device", "stats", mount], capture_output=True, text=True)
    for line in done.stdout.splitlines():
        name, _, value = line.rpartition(" ")
        key = name.strip().rsplit(".", 1)[-1]
        if key in out and value.strip().isdigit():
            out[key] += int(value)
    return out


def damaged_files(mount: str, since: float) -> list[str]:
    """Files the kernel said failed their checksums since `since`."""
    if conf.TEST:
        return []
    try:
        done = subprocess.run(["journalctl", "-k", "-o", "cat", "--no-pager", "--since", f"@{int(since)}"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    roots, found = {}, []
    for line in done.stdout.splitlines():
        m = PATH_RE.search(line) if "BTRFS" in line and "(path: " in line else None
        if not m:
            continue
        root = m.group("root")
        if root not in roots:
            sub = subprocess.run(["btrfs", "inspect-internal", "subvolid-resolve", root, mount],
                                 capture_output=True, text=True).stdout.strip()
            roots[root] = sub if root != "5" else ""
        path = "/".join(p for p in (roots[root], m.group("path").lstrip("/")) if p)
        if path not in found:
            found.append(path)
            if len(found) >= MAX_FILES:
                break
    return found


# --- the record --------------------------------------------------------------

def _damage(part: dict) -> bool:
    errors = part.get("errors") or {}
    bad = sum(int(errors.get(k) or 0) for k in ("csum_errors", "uncorrectable_errors",
                                                "verify_errors", "super_errors"))
    return bool(bad or part.get("files"))


def _device_new(record: dict) -> dict:
    """Counters since this pass began (they never reset by themselves)."""
    now, base = record.get("device") or {}, record.get("device_base")
    if not isinstance(base, dict):
        return {k: int(now.get(k) or 0) for k in DEVICE}
    return {k: max(0, int(now.get(k) or 0) - int(base.get(k) or 0)) for k in DEVICE}


def verdict(record: dict) -> str:
    if not record.get("checked_at") and not record.get("running"):
        return "unknown"
    previous = record.get("previous") or {}
    devices = [_device_new(record), previous.get("device_new") or {}]
    errors = [record.get("errors") or {}, previous.get("errors") or {}]
    if _damage(record) or _damage(previous) or any(int(d.get("corruption_errs") or 0) for d in devices):
        return "damaged"
    if any(int(d.get(k) or 0) for d in devices
           for k in ("read_io_errs", "write_io_errs", "flush_io_errs", "generation_errs")):
        return "warning"
    if any(int(e.get("read_errors") or 0) for e in errors):
        return "warning"
    return "healthy"


def start(bid: str, mount: str, minutes: int) -> dict:
    """Tonight's slice: resume a paused pass, or begin a new one."""
    record, now = load(bid), time.time()
    status = scrub_status(mount, bid)
    if status["status"] == "running":
        return record
    new_pass = status["status"] in ("none", "finished") or not record.get("pass_started")
    if new_pass:
        if record.get("full_pass_at"):
            record["previous"] = {k: record.get(k) for k in ("errors", "files", "full_pass_at")}
            record["previous"]["device_new"] = _device_new(record)
        record.update(pass_started=int(now), files=[], errors={}, device_base=device_stats(mount))
    record.update(running=True, night_started=int(now), deadline=int(now + minutes * 60))
    save(bid, record)
    code, err = scrub("start" if new_pass else "resume", mount, bid)
    if code != 0 and not new_pass:
        record.update(pass_started=int(now), files=[], errors={}, device_base=device_stats(mount))
        code, err = scrub("start", mount, bid)
    if code != 0:
        record.update(running=False, problem=err.strip()[:300])
    save(bid, record)
    return record


def settle(bid: str, mount: str, stop: bool = False) -> dict:
    """Fold what the scrub found into the record; with stop, pause it first."""
    record = load(bid)
    status = scrub_status(mount, bid)
    if stop and status["status"] == "running":
        scrub("cancel", mount, bid)
        for _ in range(30):
            status = scrub_status(mount, bid)
            if status["status"] != "running":
                break
            time.sleep(1)
    now = int(time.time())
    if stop:
        record.pop("paused_by", None)
    # Paused for a backup is still under way, not over for the night.
    running = status["status"] == "running" or bool(record.get("paused_by"))
    record["errors"] = {k: int(status.get(k, 0)) for k in ERRORS}
    record["device"] = device_stats(mount)
    record["done_bytes"] = int(status.get("data_bytes_scrubbed", 0)) + int(status.get("tree_bytes_scrubbed", 0))
    record["running"] = running
    files = list(record.get("files") or [])
    for f in damaged_files(mount, record.get("night_started") or now):
        if f not in files:
            files.append(f)
    record["files"] = files[:MAX_FILES]
    if not running:
        record["checked_at"] = now
        record.pop("deadline", None)
        if status["status"] == "finished":
            record["full_pass_at"] = now
            record.pop("previous", None)
    record["state"] = verdict(record)
    record.pop("problem", None)
    save(bid, record)
    return record
