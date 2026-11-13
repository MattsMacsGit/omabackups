"""Scenario tests (SPEC-2.0.md §18): whole stories across the product, one per
behaviour the audit found missing (notes in the kit: AUDIT-1x-vs-2.0.md).

On 13 Nov 2026 a Quick-rescued system backed up over its backup and deleted
folders from the working copy. Every unit test passed: 1.x's guards were
simply absent. These tests tell the story end to end instead.

Each one is written to FAIL FIRST, marked `to_build` (a strict expected
failure). When its behaviour is built the test passes, pytest reports the
unexpected pass as a failure, and the marker comes off: that's the sign the
spec's TO BUILD became built.
"""

import io
import json
import shutil
import sys
from types import SimpleNamespace

import pytest
from gate_harness import make_pubkey
from test_gate import KEY, owned, server  # noqa: F401  (fixtures)
from test_gate_data import tree
from test_run import latest, same, world  # noqa: F401  (world: the fixture)

from omabackups.backup import run
from omabackups.commands import backup as backup_cmd
from omabackups.commands import points as points_cmd
from omabackups.core import flow, rootjob, state
from omabackups.core.errors import OmaError
from omabackups.core.events import Events
from omabackups.restore import system as restore_system
from omabackups.root import jobs


def to_build(spec: str):
    return pytest.mark.xfail(strict=True, reason=f"TO BUILD: SPEC-2.0.md {spec}")


# --- the story's pieces -------------------------------------------------------

def points(box) -> list[str]:
    return sorted(p.name for p in (box / "points").iterdir())


def kept(box) -> str:
    """The backup's kept restore points, as the server holds them."""
    return (box / "kept.json").read_text()


def quick_rescued(sandbox, src, point: str) -> None:
    """What a Quick Rescue leaves behind (restore/system.py): settings back,
    the folders still on the backup. rescued.json for the system, and
    migrate.json in the home with the folders still to come."""
    homes = sandbox.sysroot / "home"
    homes.mkdir(exist_ok=True)
    (homes / "u").symlink_to(sandbox.home)
    (sandbox.home / "Documents").mkdir(exist_ok=True)
    restore_system._record(sandbox.sysroot, point, full=False)
    (src.root / "home/u/notes.txt").unlink()          # still on the backup, not here


def migrated(point: str) -> None:
    """What Migrate my saved config leaves behind: apps and settings here,
    the folders picked still to come back."""
    state.write(flow.MIGRATE, {"done": True, "files_restored": False, "rescued": False, "point": point,
                               "from_user": "u", "files": ["Documents"], "at": 1, "version": 1})


def still_in_working_copy(box) -> bool:
    return (box / "current/001/home/u/notes.txt").exists()


# --- §9: the guards after a Quick Rescue or a Migrate -------------------------

@to_build("§9 (audit 1.2): automatic backups paused after a Quick Rescue")
def test_a_quick_rescued_system_never_backs_up_on_its_own(world, sandbox, monkeypatch):
    srv, kid, bid, src, box = world
    first = run.backup(source=src)["point"]
    quick_rescued(sandbox, src, first)
    # Even with nothing else waiting (a Back up now ended D29's wait), and due.
    run.save_record({**run.load_record(), "automatic_paused": False, "last_finished": 0})
    real = run.backup
    monkeypatch.setattr(run, "backup", lambda *a, **k: real(*a, source=src, **k))
    assert backup_cmd.run_root(SimpleNamespace(kind="scheduled"), Events()) == 0
    assert points(box) == [first]
    assert still_in_working_copy(box)


@to_build("§9 (audit 1.3): Back up now refused after a Quick Rescue, with what to do")
def test_a_quick_rescued_system_refuses_back_up_now(world, sandbox):
    srv, kid, bid, src, box = world
    first = run.backup(source=src)["point"]
    quick_rescued(sandbox, src, first)
    with pytest.raises(OmaError) as refused:
        run.backup(source=src)
    assert refused.value.code == "partial-restore"
    assert "Restore my files" in refused.value.todo
    assert points(box) == [first]
    assert still_in_working_copy(box)          # nothing deleted from the backup


@to_build("§9 + §8 (audit 1.5, 9.2): the deliberate override keeps the rescue's point")
def test_a_forced_backup_after_a_rescue_keeps_its_point(world, sandbox):
    srv, kid, bid, src, box = world
    first = run.backup(source=src)["point"]
    quick_rescued(sandbox, src, first)
    result = run.backup(source=src, force_after_restore=True)
    assert result["point"] != first
    assert first in kept(box)                  # what never came back is still there
    assert not still_in_working_copy(box)      # the override did what it says


@to_build("§9 (audit 6.1): the same guard after a Migrate")
def test_a_migrate_refuses_a_backup_until_its_folders_are_back(world):
    srv, kid, bid, src, box = world
    first = run.backup(source=src)["point"]
    migrated(first)
    (src.root / "home/u/notes.txt").unlink()
    with pytest.raises(OmaError) as refused:
        run.backup(source=src)
    assert refused.value.code == "partial-restore"
    assert points(box) == [first]
    assert still_in_working_copy(box)


# --- §8: keeping, deleting, rebuilding ------------------------------------------

@to_build("§8 (audit 1.4): the rescue keeps its point the moment it's picked")
def test_the_point_a_rescue_came_from_is_kept(owned):  # noqa: F811
    server, kid, bid = owned
    rescue = server.ok(kid, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    inside = server.root / "data/store" / f"{bid}.box" / "inside"
    for name in ("001-2026-11-01-1000", "001-2026-11-02-1000"):
        (inside / "points" / name).mkdir()
    server.ok(rescue, f"unlock {bid}", KEY)
    server.ok(rescue, f"keep {bid} 001-2026-11-01-1000")          # picked on the stick
    info = server.ok(kid, f"points {bid}")
    assert "001-2026-11-01-1000" in json.dumps(info["kept"])
    assert "rescue" in json.dumps(info["kept"])                    # shown as R (audit 9.3)
    assert server.call(kid, f"delete {bid} 001-2026-11-01-1000")[0] == 1   # thinning can't either


def test_deleting_the_newest_point_works(world, monkeypatch):
    srv, kid, bid, src, box = world
    names = iter(["001-2099-01-01-0000", "001-2099-01-02-0000"])
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    run.backup(source=src)
    newest = run.backup(source=src)["point"]
    jobs._jobs()["delete-point"]({"point": newest, "any": True})      # the command line, once it asked
    assert points(box) == ["001-2099-01-01-0000"]


def test_delete_asks_first(sandbox, monkeypatch):
    asked = []
    monkeypatch.setattr(rootjob, "run", lambda job, request: asked.append(job) or {})
    monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))
    points_cmd.run_delete(SimpleNamespace(point="001-2099-01-02-0000"), Events())
    assert asked == []                         # "no": nothing deleted
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    points_cmd.run_delete(SimpleNamespace(point="001-2099-01-02-0000"), Events())
    assert asked == ["delete-point"]


def test_rebuild_from_repairs_a_damaged_working_copy(world, monkeypatch):
    srv, kid, bid, src, box = world
    names = iter(["001-2099-01-01-0000", "001-2099-01-02-0000", "001-2099-01-03-0000"])
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    good = run.backup(source=src)["point"]
    (box / "current/001/home/u/notes.txt").write_text("damaged")     # 13 Nov, in small
    shutil.rmtree(box / "current/001/system")
    jobs._jobs()["rebuild-from"]({"point": good})
    assert tree(box / "current/001") == tree(box / "points" / good)
    run.backup(source=src)                                            # checks once, sends what changed
    same(latest(box), src)


# --- §6 + §10: damaged files ----------------------------------------------------

@to_build("§6 + §10 (audit 4.3): a damaged file is never reused")
def test_a_damaged_file_is_not_reused(world, monkeypatch):
    srv, kid, bid, src, box = world
    names = iter(f"001-2099-01-0{i}-0000" for i in range(1, 9))
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    (src.root / "home/u/manual.pdf").write_bytes(b"P" * 40_000)
    first = run.backup(source=src)["point"]
    copy = box / "points" / first / "home/u/manual.pdf"
    (src.root / "home/u/manual.pdf").unlink()
    run.backup(source=src)
    shutil.copy2(copy, src.root / "home/u/manual.pdf")                # Restore my files
    health = next(srv.root.rglob("registry.json")).parent / "health" / f"{bid}.json"
    health.parent.mkdir(parents=True, exist_ok=True)
    health.write_text(json.dumps({"state": "damaged",
                                  "files": [f"inside/points/{first}/home/u/manual.pdf"]}))
    answers = []
    real = run.reuse.ask
    monkeypatch.setattr(run.reuse, "ask", lambda *a: answers.append(real(*a)) or answers[-1])
    run.backup(source=src)
    assert all(a["files"] == 0 for a in answers)                      # sent fresh, not cloned
    same(latest(box), src)
