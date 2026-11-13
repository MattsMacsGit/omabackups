"""D52: after a Quick Rescue, folders come back as you choose, as often as you
like; the Finish restore page stays until a backup ends it."""

import json
from types import SimpleNamespace

from omabackups.commands import restore as restore_cmd
from omabackups.commands import status_data
from omabackups.core import flow, paths, rootjob, state

RESCUED = {"done": True, "files_restored": False, "rescued": True, "point": "001-2026-11-12-1955",
           "from_user": "u", "files": ["Documents", "Music", "Pictures"], "at": 1_000_000}


def _record(last_finished: int) -> None:
    record = paths.system_state_dir() / "backup.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"last_point": "001-2026-11-12-1955", "last_finished": last_finished}))


def _restored(only) -> None:
    paths.system_run_dir().mkdir(parents=True, exist_ok=True)
    (paths.system_run_dir() / "restore.json").write_text(json.dumps(
        {"point": RESCUED["point"], "done": True, "running": False, "only": only}))


def test_the_page_stays_until_a_backup_after_the_rescue(sandbox):
    state.write(flow.MIGRATE, {**RESCUED, "files_restored": True, "brought": RESCUED["files"]})
    _record(last_finished=900_000)                     # the rescued point's own record: older
    assert flow.where() is flow.Step.RESTORE_FILES     # all back, but no backup yet
    _record(last_finished=1_000_500)
    assert flow.where() is not flow.Step.RESTORE_FILES


def test_a_finished_run_doesnt_end_the_page(sandbox):
    state.write(flow.MIGRATE, RESCUED)
    _record(last_finished=900_000)
    _restored(None)
    assert status_data._migrate()["files_restored"] is True
    assert flow.where() is flow.Step.RESTORE_FILES      # still here: back up to finish


def test_the_ticked_folders_are_what_is_asked_for(sandbox, monkeypatch):
    state.write(flow.MIGRATE, RESCUED)
    asked = {}
    monkeypatch.setattr(rootjob, "run", lambda job, request: asked.update(job=job, request=request) or {})

    class Events:
        def result(self, *a):
            pass
    restore_cmd.run_restore(SimpleNamespace(point=RESCUED["point"], only=["Music", "Music", "Pictures"]),
                            Events())
    assert asked["request"]["only"] == ["Music", "Pictures"] and asked["request"]["from_user"] == "u"
