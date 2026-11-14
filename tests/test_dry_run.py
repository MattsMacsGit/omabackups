"""`omabackups backup --dry-run` (audit 2.8): what a backup now would send
and delete, with nothing changed; and each restore point says which
computer made it (audit 2.7)."""

import json
import platform
import socket

from test_run import latest, world  # noqa: F401  (world: the fixture)

from omabackups.backup import run, todo
from omabackups.core.errors import OmaError
from omabackups.rescue import wizard


def snapshots(src) -> list[str]:
    return sorted(src.snapshots(None).names())


def test_a_dry_run_says_what_and_changes_nothing(world, monkeypatch):  # noqa: F811
    srv, kid, bid, src, box = world
    monkeypatch.setattr(run, "point_name", lambda line, latest: "001-2099-01-01-0000")
    run.backup(source=src)
    (src.root / "home/u/notes.txt").write_text("changed, and longer")
    (src.root / "home/u/new.txt").write_text("new")
    (src.root / "system/etc/hostname").unlink()
    record, snaps, points = run.load_record(), snapshots(src), sorted(p.name for p in (box / "points").iterdir())
    working = (box / "current/001/home/u/notes.txt").read_text()

    parts = {row["part"]: row for row in run.backup(source=src, dry_run=True)["dry_run"]}
    assert parts["home"]["files"] == 2 and parts["home"]["bytes"] > 0
    assert parts["system"]["deletes"] == 1
    assert run.load_record() == record and snapshots(src) == snaps          # nothing here changed
    assert sorted(p.name for p in (box / "points").iterdir()) == points    # nor on the server
    assert (box / "current/001/home/u/notes.txt").read_text() == working
    assert todo.any_unfinished() == []


def test_a_dry_run_before_the_first_backup_keeps_no_list(world):  # noqa: F811
    srv, kid, bid, src, box = world
    parts = {row["part"]: row for row in run.backup(source=src, dry_run=True)["dry_run"]}
    assert parts["home"]["files"] >= 1
    assert todo.any_unfinished() == [] and snapshots(src) == []
    assert run.backup(source=src)["how"]["home"] == "full, checked once"     # a real one still works


def test_a_dry_run_isnt_stopped_by_the_guard_but_a_migrating_one_is(world, monkeypatch):  # noqa: F811
    srv, kid, bid, src, box = world
    from omabackups.core import partial
    monkeypatch.setattr(partial, "waiting", lambda record=None: {"point": "p", "folders": ["Music"]})
    assert run.backup(source=src, dry_run=True)["dry_run"]
    from omabackups.core import paths
    server = json.loads(paths.server_file().read_text())
    paths.server_file().write_text(json.dumps({**server, "migrating": True, "from_point": "001-x"}))
    try:
        run.backup(source=src, dry_run=True)
        raise AssertionError("a dry run took a migrating backup over")
    except OmaError as exc:
        assert exc.code == "migrating"


def test_each_point_says_which_computer_made_it(world):  # noqa: F811
    srv, kid, bid, src, box = world
    run.backup(source=src)
    info = json.loads((latest(box) / "point.json").read_text())
    assert info["computer"] == socket.gethostname() and info["kernel"] == platform.release()


def test_the_rescue_menu_names_each_line_by_its_computer():
    class Gate:
        def call(self, verb, bid, name):
            return {"point": {"computer": {"001": "laptop", "002": "desk"}.get(name[:3])}} if name[:3] != "003" \
                else {"point": {}}
    names = ["002-2026-11-14-0900", "001-2026-11-14-0800", "001-2026-11-13-0800", "003-2026-11-01-0800"]
    assert wizard.line_names(Gate(), "b", names) == {"002": "desk", "001": "laptop", "003": ""}


def test_the_command_says_it_plainly(sandbox, monkeypatch, capsys):
    from types import SimpleNamespace

    from omabackups.commands import backup as backup_cmd
    from omabackups.core import paths, rootjob
    from omabackups.core.events import Events
    paths.server_file().parent.mkdir(parents=True, exist_ok=True)
    paths.server_file().write_text("{}")
    monkeypatch.setattr(rootjob, "run", lambda job, request: {"parts": [
        {"part": "system", "files": 0, "bytes": 0, "deletes": 0, "moves": 0},
        {"part": "home", "files": 2, "bytes": 2048, "deletes": 1, "moves": 3},
        {"part": "boot", "files": None, "bytes": 512, "deletes": 0, "moves": 0}]})
    assert backup_cmd.run_now(SimpleNamespace(dry_run=True, force_after_restore=False), Events()) == 0
    out = capsys.readouterr().out
    assert "system: nothing to send" in out and "home: 2 files to send (2.0 KB), 1 to delete, 3 to move" in out
    assert "boot: 512 bytes to check and send" in out and "Nothing was changed." in out
