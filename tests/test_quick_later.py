"""What a Quick Rescue leaves for later (SPEC §12; audit 1.9, 1.11, 8.4): the
big part of the Quick skips items, never a program's settings or saves; AI
models in the system area too; Restore my files brings them back, never
touching a file that's here; the guard waits for them."""

import json
import os
import time

from test_run import world  # noqa: F401  (the fixture)

from omabackups.backup import run, skips
from omabackups.core import flow, partial, paths, state
from omabackups.restore import files, later
from omabackups.tui import quick

POINT = "001-2026-11-12-1955"


def test_a_file_here_is_never_touched_whatever_its_date(world):  # noqa: F811
    srv, kid, bid, src, box = world
    home = src.root / "home" / "u"
    point = run.backup(source=src)["point"]
    (home / "notes.txt").write_text("here, and older")
    os.utime(home / "notes.txt", (time.time() - 86400, time.time() - 86400))
    assert files.restore(point, "u", home=home).get("done")
    assert (home / "notes.txt").read_text() == "here, and older"           # 1.x: --ignore-existing


def test_ai_models_come_back_into_the_system_area(world, sandbox):  # noqa: F811
    srv, kid, bid, src, box = world
    models = src.root / "system/var/lib/ollama/models"
    models.mkdir(parents=True)
    (models / "blob").write_text("a model")
    (models / "already").write_text("from the backup")
    point = run.backup(source=src)["point"]
    here = sandbox.sysroot / "var/lib/ollama/models"
    here.mkdir(parents=True)
    (here / "already").write_text("here")
    state_ = files.restore(point, "u", home=src.root / "home" / "u")
    assert state_.get("done"), (state_.get("error") or {}).get("details")
    assert (here / "blob").read_text() == "a model"
    assert (here / "already").read_text() == "here"                         # never touched
    runs = json.loads(partial.restored_file().read_text())[point]
    assert set(runs[-1]["later"]) == set(later.LATER)


def test_left_in_the_backup_on_purpose_stays_there(world, sandbox):  # noqa: F811
    srv, kid, bid, src, box = world
    (src.root / "system/var/lib/ollama").mkdir(parents=True)
    (src.root / "system/var/lib/ollama/blob").write_text("a model")
    point = run.backup(source=src)["point"]
    files.restore(point, "u", home=src.root / "home" / "u", leave_out=["/.ollama/models"],
                  leave_out_system=["/var/lib/ollama"])
    assert not (sandbox.sysroot / "var/lib/ollama/blob").exists()
    assert "models" not in json.loads(partial.restored_file().read_text())[point][-1]["later"]


def test_the_guard_waits_for_the_quick_skips_items(sandbox):
    state.write(flow.MIGRATE, {"done": True, "files_restored": False, "rescued": True, "point": POINT,
                               "files": ["Music"], "later": list(later.LATER), "at": 1})
    partial.note_restored(POINT, ["Music"], [])
    assert partial.waiting()["folders"] == ["AI models", "Game libraries", "Flatpak apps",
                                            "Virtual machines & containers"]
    partial.note_restored(POINT, None, ["/.lmstudio/models"], later.brought(None, ["/.lmstudio/models"], []))
    assert partial.waiting()["folders"] == ["AI models"]                    # left on purpose: Ctrl
    partial.note_restored(POINT, None, [], later.brought(None, [], []))
    assert partial.waiting() is None


def test_a_switch_that_was_on_stays_on_with_the_narrower_rules(sandbox):
    """Game libraries and VMs skipped whole folders before 14 Nov; now only
    the part you can get again. A saved list reads the new way."""
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    (paths.system_config_dir() / "skips.json").write_text(json.dumps({"format": 2, "system": [], "home": [
        ".cache", "/u/.steam", "/u/.local/share/Steam", "/u/.local/share/bottles", "/u/Videos"]}))
    rules = skips.patterns_for("home")
    assert rules[0] == ".cache" and rules[-1] == "/u/Videos"
    assert all(r in rules for r in quick.STEAM)
    assert "/u/.local/share/bottles/runners" in rules and "/u/.local/share/bottles" not in rules
    assert "/u/.steam" not in rules and "/u/.local/share/Steam" not in rules
