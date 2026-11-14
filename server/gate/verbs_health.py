"""The health check's verbs (D18).

  health-start BACKUP MINUTES   tonight's slice (owner; the backup must be unlocked)
  health BACKUP                 the verdict and progress (owner or rescue; works locked)
"""

import time

import health
import registry
from host import host, mountpoint
from registry import Refused


def _argc(call, n: int) -> None:
    if len(call.args) != n:
        raise Refused("wrong number of arguments")


def v_health_start(call):
    _argc(call, 2)
    bid, minutes = call.args
    registry.the_backup(registry.load(), bid, call.kid, ("owner",))
    if not minutes.isdigit() or not 1 <= int(minutes) <= 720:
        raise Refused("minutes must be from 1 to 720")
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    record = health.start(bid, str(mountpoint(bid)), int(minutes))
    return _shown(record)


def v_health(call):
    _argc(call, 1)
    bid = call.args[0]
    registry.the_backup(registry.load(), bid, call.kid, ("owner", "rescue"))
    record = health.load(bid)
    if record.get("running") and host().is_mounted(bid):
        record = health.settle(bid, str(mountpoint(bid)))
    return _shown(record)


def _shown(record: dict) -> dict:
    state = health.verdict(record)
    if state == "healthy" and not record.get("full_pass_at") and not record.get("done_bytes"):
        state = "unknown"     # nothing has been read yet: never call that healthy
    return {"state": state, "running": bool(record.get("running")),
            "done_bytes": record.get("done_bytes", 0), "checked_at": record.get("checked_at"),
            "full_pass_at": record.get("full_pass_at"), "pass_started": record.get("pass_started"),
            "damaged": len(record.get("files") or []), "files": (record.get("files") or [])[:20],
            "paths": record.get("files") or [],      # every one, for sending them again (gate 19)
            "problem": record.get("problem")}


def before_lock(bid: str) -> None:
    """A check under way is paused (not lost) before the box locks."""
    if health.load(bid).get("running"):
        health.settle(bid, str(mountpoint(bid)), stop=True)


def pause_for(bid: str, hid: str) -> None:
    """A backup is about to write: tonight's check stands aside, keeping its place
    (the two fighting over one disk slows both; 1.x)."""
    record = health.load(bid)
    mount = str(mountpoint(bid))
    if not record.get("running") or record.get("paused_by"):
        return
    if health.scrub_status(mount, bid)["status"] != "running":
        return
    health.scrub("cancel", mount, bid)
    for _ in range(30):
        if health.scrub_status(mount, bid)["status"] != "running":
            break
        time.sleep(1)
    record["paused_by"] = hid
    health.save(bid, record)


def carry_on(bid: str) -> None:
    """The backup is done: the check picks up again (if tonight's time isn't up)."""
    record = health.load(bid)
    if not record.pop("paused_by", None):
        return
    health.save(bid, record)
    mount = str(mountpoint(bid))
    if time.time() < float(record.get("deadline") or 0):
        health.scrub("resume", mount, bid)
    else:
        health.settle(bid, mount, stop=True)


def keep_open(bid: str) -> bool:
    """For the sweep: True while tonight's check should go on (box stays open)."""
    import holds
    record = health.load(bid)
    if not record.get("running"):
        return False
    if record.get("paused_by"):
        if record["paused_by"] not in holds.live(bid):   # the backup is gone (even if it died)
            carry_on(bid)
        return True
    mount = str(mountpoint(bid))
    if health.scrub_status(mount, bid)["status"] != "running":
        health.settle(bid, mount)           # it finished (or stopped) by itself
        return False
    if time.time() >= float(record.get("deadline") or 0):
        health.settle(bid, mount, stop=True)  # tonight's time is up: carry on tomorrow
        return False
    return True


VERBS = {"health-start": v_health_start, "health": v_health}
