"""Notifications, battery and an unreachable backup (SPEC §7; audit 3.5,
3.6, 3.7; 1.x schedule.sh, lib/common.sh notify_user)."""

import json
import time
from types import SimpleNamespace

import pytest

from omabackups.backup import run
from omabackups.commands import backup as backup_cmd
from omabackups.core import flow, notify, paths, power, state
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def shown() -> list:
    log = paths.system_state_dir() / "notifications.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def battery(sandbox, status: str, capacity: int) -> None:
    bat = sandbox.sysroot / "sys/class/power_supply/BAT0"
    bat.mkdir(parents=True, exist_ok=True)
    (bat / "type").write_text("Battery\n")
    (bat / "status").write_text(status + "\n")
    (bat / "capacity").write_text(f"{capacity}\n")


def set_up(last_finished=None) -> None:
    paths.server_file().parent.mkdir(parents=True, exist_ok=True)
    paths.server_file().write_text("{}")
    run.save_record({"last_finished": last_finished, "last_point": "001-2026-11-14-0900"} if last_finished
                    else {"last_point": "001-2026-11-14-0900"})


def scheduled() -> int:
    return backup_cmd.run_root(SimpleNamespace(kind="scheduled"), Events())


def test_each_kind_at_most_once_a_day(sandbox):
    assert notify.send("A", "a", "k") and not notify.send("A", "a", "k")
    assert notify.send("B", "b", "other")
    assert shown() == [["A", "a"], ["B", "b"]]


def test_overdue_after_three_intervals(sandbox):
    now = time.time()
    assert not notify.overdue("Why.", 3600, now - 2 * 3600, now)
    assert notify.overdue("Why.", 3600, now - 3 * 3600, now)
    title, body = shown()[-1]
    assert title == "No backup for a while" and body.startswith("Last backup: ") and body.endswith(". Why.")


def test_the_battery_under_20_while_discharging(sandbox):
    assert not power.low_battery()
    battery(sandbox, "Discharging", 19)
    assert power.low_battery()
    battery(sandbox, "Charging", 5)
    assert not power.low_battery()


def test_on_a_low_battery_an_automatic_backup_waits(sandbox, monkeypatch):
    set_up()
    battery(sandbox, "Discharging", 10)
    monkeypatch.setattr(run, "backup", lambda *a, **k: pytest.fail("backed up on a low battery"))
    assert scheduled() == 0
    assert shown() == [["No backup for a while", "Last backup: never. The battery is under 20%."]]


def test_unreachable_is_skipped_quietly(sandbox, monkeypatch):
    set_up()

    def away(*a, **k):
        raise OmaError("Your backup can't be reached.", code="unreachable")
    monkeypatch.setattr(run, "backup", away)
    assert scheduled() == 0                                  # not a failure every hour
    assert shown()[-1][1].endswith("Your backup can't be reached.")
    from omabackups.backup import progress
    assert progress.read()["error"]["code"] == "unreachable"  # the panel's yellow line stays true


def test_a_failed_automatic_backup_says_so_when_overdue(sandbox, monkeypatch):
    set_up()

    def broken(*a, **k):
        raise OmaError("Something broke.", code="send-failed")
    monkeypatch.setattr(run, "backup", broken)
    with pytest.raises(OmaError):
        scheduled()
    assert shown()[-1][1].endswith("The last automatic backup failed.")


def test_paused_after_a_rescue_says_so(sandbox):
    set_up()
    state.write(flow.MIGRATE, {"done": True, "files_restored": False, "rescued": True,
                               "point": "001-2026-11-14-0900", "files": ["Music"], "at": 1})
    assert scheduled() == 0
    assert shown() == [list(notify.PAUSED)]


def test_nearly_full_and_damage_after_a_backup(sandbox):
    run.save_record({"space": {"box": 100, "used": 95, "free": 5}})
    from omabackups.backup import health
    health.save({"state": "damaged"})
    backup_cmd.after_backup()
    assert shown() == [list(notify.FULL), list(notify.DAMAGE)]
