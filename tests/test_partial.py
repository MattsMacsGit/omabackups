"""The guard after a partial restore (SPEC-2.0.md §9): which folders are back,
when it lifts, and who checks it. The whole stories are in test_scenarios.py."""

import json
from types import SimpleNamespace

import pytest

from omabackups.commands import backup as backup_cmd
from omabackups.core import flow, partial, paths, state
from omabackups.core.errors import OmaError
from omabackups.core.events import Events
from omabackups.restore import system as restore_system

POINT = "001-2026-11-12-1955"


def rescued(files=("Documents", "Music", "Pictures")) -> None:
    state.write(flow.MIGRATE, {"done": True, "files_restored": False, "rescued": True, "point": POINT,
                               "from_user": "u", "files": list(files), "at": 1})


def test_a_folder_is_back_only_when_all_of_it_came():
    assert partial.is_back("Music", [{"only": None, "leave_out": []}])
    assert partial.is_back("Music", [{"only": ["Music"], "leave_out": []}])
    assert not partial.is_back("Music", [{"only": ["Music/Live"], "leave_out": []}])     # part of it
    assert not partial.is_back("Music", [{"only": None, "leave_out": ["Music/big.flac"]}])
    assert not partial.is_back("Musical", [{"only": ["Music"], "leave_out": []}])
    assert partial.is_back("Music", [{"only": ["Pictures"], "leave_out": []}, {"only": ["Music"]}])


def test_some_folders_back_still_waits_all_back_lifts(sandbox):
    rescued()
    assert partial.waiting()["folders"] == ["Documents", "Music", "Pictures"]
    partial.note_restored(POINT, ["Music"], [])
    partial.note_restored(POINT, ["Documents"], [])
    assert partial.waiting() == {"point": POINT, "folders": ["Pictures"], "rescued": True}
    partial.note_restored(POINT, ["Pictures"], [])
    assert partial.waiting() is None


def test_another_points_restores_dont_count(sandbox):
    rescued()
    partial.note_restored("001-2026-11-01-1000", None, [])
    assert partial.waiting()


def test_a_forced_backup_lifts_it(sandbox):
    rescued()
    assert partial.waiting(record={"forced_past": POINT}) is None
    assert partial.waiting(record={"forced_past": "001-2026-01-01-0000"})


def test_nothing_waits_without_folders_to_come(sandbox):
    assert partial.waiting() is None                        # never rescued or migrated
    rescued(files=())                                       # a Full Rescue
    assert partial.waiting() is None
    state.write(flow.MIGRATE, {"done": False, "files": ["Documents"], "point": POINT})
    assert partial.waiting() is None                        # Migrate not finished: its own page


def test_back_up_now_says_why_before_starting_anything(sandbox, monkeypatch):
    rescued()
    paths.server_file().parent.mkdir(parents=True, exist_ok=True)
    paths.server_file().write_text("{}")
    monkeypatch.setattr(backup_cmd, "start", lambda kind: pytest.fail("a service started"))
    with pytest.raises(OmaError) as refused:
        backup_cmd.run_now(SimpleNamespace(force_after_restore=False), Events())
    assert refused.value.code == "partial-restore"
    assert "Documents, Music, Pictures" in refused.value.todo
    assert "--force-after-restore" in refused.value.todo
    started = []
    monkeypatch.setattr(backup_cmd, "_start_and_follow", lambda kind, events: started.append(kind) or 0)
    backup_cmd.run_now(SimpleNamespace(force_after_restore=True), Events())
    assert started == ["forced"]


def test_the_health_check_waits_too(sandbox, monkeypatch):
    rescued()
    paths.server_file().parent.mkdir(parents=True, exist_ok=True)
    paths.server_file().write_text("{}")
    monkeypatch.setattr(backup_cmd.health, "due", lambda *a: pytest.fail("checked whether it's due"))
    assert backup_cmd.run_health(SimpleNamespace(), Events()) == 0


def test_a_rescue_leaves_automatic_backups_waiting(sandbox, tmp_path):
    root = tmp_path / "newdisk"
    old = root / "var/lib/omabackups"
    old.mkdir(parents=True)
    (old / "backup.json").write_text(json.dumps({"last_point": POINT, "automatic_paused": False,
                                                 "forced_past": POINT}))
    (old / "restored.json").write_text(json.dumps({POINT: [{"only": None}]}))
    restore_system._record(root, POINT, full=True)
    record = json.loads((old / "backup.json").read_text())
    assert record["automatic_paused"] is True and "forced_past" not in record
    assert record["last_point"] == POINT
    assert not (old / "restored.json").exists()


def test_the_panel_stays_on_finish_restore_while_it_waits(sandbox):
    rescued()
    record = paths.system_state_dir() / "backup.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"last_point": POINT, "last_finished": 2}))   # a backup since (13 Nov)
    assert flow.where() is flow.Step.RESTORE_FILES
    for folder in ("Documents", "Music", "Pictures"):
        partial.note_restored(POINT, [folder], [])
    assert flow.where() is not flow.Step.RESTORE_FILES
