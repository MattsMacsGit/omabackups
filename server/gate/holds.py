"""Unlocked only while someone needs it (D6; 1.x's holds, kept).

Each job that unlocks a backup gets a hold; the backup locks again once the
last hold is gone AND the box has been quiet for IDLE_LOCK (the sweep, from a
timer). Lessons from 1.x, kept:
- unlock and lock take turns per backup (a lock arriving mid-unlock used to
  find nothing open, lock nothing, and the unlock then left it open);
- the gatekeeper hands out hold IDs, so a caller can only drop its own;
- a hold nothing refreshes goes stale (its job died without saying so);
- a forced lock leaves a note before queueing, so the unlock it raced still
  locks up after itself;
- holds live on /run, not in the box: a locked box can't be read, and a
  reboot rightly forgets them.
"""

import fcntl
import os
import secrets
import time
from contextlib import contextmanager

import conf


def _dir(bid: str):
    return conf.RUN / "holds" / bid


@contextmanager
def turn(bid: str):
    folder = conf.RUN / "turns"
    folder.mkdir(parents=True, exist_ok=True)
    fd = os.open(folder / f"{bid}.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def live(bid: str) -> list[str]:
    """Holds still worth honouring; stale ones are dropped (call inside the turn)."""
    now, alive = time.time(), []
    try:
        names = sorted(p.name for p in _dir(bid).iterdir() if conf.HOLD_ID.match(p.name))
    except OSError:
        return []
    for name in names:
        path = _dir(bid) / name
        try:
            if now - path.stat().st_mtime <= conf.HOLD_STALE:
                alive.append(name)
            else:
                path.unlink()
        except OSError:
            pass
    return alive


def add(bid: str) -> str:
    folder = _dir(bid)
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    hid = secrets.token_hex(8)
    (folder / hid).touch()
    return hid


def refresh(bid: str, hid: str) -> bool:
    try:
        os.utime(_dir(bid) / hid)
        return True
    except OSError:
        return False


def drop(bid: str, hid: str) -> None:
    (_dir(bid) / hid).unlink(missing_ok=True)


def drop_all(bid: str) -> None:
    for hid in live(bid):
        drop(bid, hid)


def _wanted(bid: str):
    return conf.RUN / "turns" / f"{bid}.lock-wanted"


def want_lock(bid: str) -> None:
    (conf.RUN / "turns").mkdir(parents=True, exist_ok=True)
    _wanted(bid).touch()


def lock_wanted_since(bid: str, started: float) -> bool:
    """A forced lock asked after `started`. Older notes are junk: cleared, not obeyed."""
    try:
        fresh = _wanted(bid).stat().st_mtime >= started
    except OSError:
        return False
    _wanted(bid).unlink(missing_ok=True)
    return fresh


def clear_wanted(bid: str) -> None:
    _wanted(bid).unlink(missing_ok=True)


def quiet_long_enough(bid: str, activity: str | None, now: float | None = None) -> bool:
    """Has the box's activity stayed the same for IDLE_LOCK? Starts the clock if not."""
    now = time.time() if now is None else now
    stamp = conf.RUN / "turns" / f"{bid}.quiet"
    try:
        since_text, _, was = stamp.read_text(encoding="utf-8").partition("\n")
        since = float(since_text)
    except (OSError, ValueError):
        since, was = None, None
    if since is not None and activity is not None and activity == was:
        return now - since >= conf.IDLE_LOCK
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(f"{now}\n{activity or ''}", encoding="utf-8")
    return False


def reset_quiet(bid: str) -> None:
    (conf.RUN / "turns" / f"{bid}.quiet").unlink(missing_ok=True)
