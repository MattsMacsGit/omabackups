"""D49 C: a full backup checks once, then knows where it's up to. Cut off,
the next run carries on from its to-do list and btrfs's changes, with no
check over the network; the result is still an exact copy."""

import json
import os
import sys

import pytest
from test_run import holds_left, latest, same, world  # noqa: F401 - world is a fixture

from omabackups.backup import progress, run, todo
from omabackups.backup.send import Sender
from omabackups.core import paths
from omabackups.core.errors import OmaError


def _more_files(src, n=12):
    for i in range(n):
        p = src.root / f"home/u/Documents/file{i:02d}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"contents {i} " * 50)


def _cut_off_home_half_way(monkeypatch):
    real = Sender.copy

    def half(self, part, source, items, already=0):
        if part != "home":
            return real(self, part, source, items, already)
        files = [i for i in items if i[1] > 0]
        real(self, part, source, files[: len(files) // 2], already)
        raise OmaError("network gone", code="send-failed")
    monkeypatch.setattr(Sender, "copy", half)
    return real


def test_a_cut_off_full_backup_carries_on_without_checking_again(world, monkeypatch):
    srv, kid, bid, src, box = world
    _more_files(src)
    real = _cut_off_home_half_way(monkeypatch)
    with pytest.raises(OmaError):
        run.backup(source=src)
    assert run.load_record()["finished"] is False
    meta, items = todo.load("home")
    left = todo.remaining("home")
    assert 0 < len(left) < len(items)                       # half ticked off
    assert holds_left(srv, bid) == []
    # Its snapshot was kept for the next run (a failed run drops only the others).
    assert (src.root / "snaps" / meta["snapshot"]).is_dir()

    # Meanwhile: a sent file changes, another is deleted, a new one arrives.
    (src.root / "home/u/Documents/file00.txt").write_text("changed since")
    (src.root / "home/u/Documents/file01.txt").unlink()
    (src.root / "home/u/later.txt").write_text("new since")

    monkeypatch.setattr(Sender, "copy", real)

    def no_check(*args, **kwargs):
        raise AssertionError("it checked over the network again")
    monkeypatch.setattr(Sender, "check", no_check)
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    again = run.backup(source=src)
    assert again["how"]["home"] == "full, carried on"
    same(latest(box), src)                                  # still an exact copy
    assert todo.any_unfinished() == []                      # finished: the lists go
    assert run.load_record()["finished"] is True


def test_a_list_that_no_longer_fits_is_checked_again(world, monkeypatch):
    srv, kid, bid, src, box = world
    _more_files(src)
    real = _cut_off_home_half_way(monkeypatch)
    with pytest.raises(OmaError):
        run.backup(source=src)
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    (paths.system_config_dir() / "skips.json").write_text(json.dumps({"home": ["notes.txt"]}))
    monkeypatch.setattr(Sender, "copy", real)
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    again = run.backup(source=src)
    assert again["how"]["home"] == "full, checked once"
    assert not (latest(box) / "home/u/notes.txt").exists()


def test_the_check_lists_what_it_would_send_and_delete():
    out = (b"building file list ...\n"
           b"OMA|>f+++++++++|2048|Documents/a.txt\n"
           b"OMA|cd+++++++++|4096|Documents/\n"
           b"OMA|*deleting  |0|old/gone.txt\n"
           b"OMA|<f.st......|10|odd\\#012name\n"
           b"OMA|.d..t......|4096|./\n"
           b"Total file size: 1,234 bytes\n")
    items, deletes = todo.parse_check(out)
    assert items == [("Documents/a.txt", 2048), ("Documents", 0), ("odd\nname", 10)]
    assert deletes == ["old/gone.txt"]


def test_unticked_items_follow_renames_and_drop_deletes(tmp_path):
    from omabackups.backup.changes import Plan
    snap = tmp_path / "snap"
    (snap / "new/place").mkdir(parents=True)
    (snap / "new/place/a.txt").write_text("aaaa")
    (snap / "fresh.txt").write_text("f")
    plan = Plan(ops=[["rename", "old/place", "new/place"], ["delete", "gone"]], files=["fresh.txt"])
    left = [("old/place/a.txt", 4), ("gone/b.txt", 9)]
    assert todo.carry(left, plan, str(snap)) == [("fresh.txt", 1), ("new/place/a.txt", 4)]


def test_progress_reads_as_a_sentence():
    state = {"step": "send", "part": "home", "part_no": 2, "parts": 3, "percent": 42,
             "sent": 12_400_000_000, "total": 310_000_000_000, "speed": 48_000_000, "left": 6600}
    assert progress.text(state) == ("Backing up home... 42% · 12.4 GB of 310 GB · 48.0 MB/s · "
                                    "about 1 h 50 min left (part 2 of 3)")
    assert progress.text({"step": "check", "part": "home"}) == "Checking home..."


def test_rsync_that_moves_nothing_for_3_minutes_is_stopped(monkeypatch, tmp_path):
    """Stuck: no bytes, no file finished. (The clock stops while asleep.)"""
    from omabackups.backup import meter as meter_mod
    monkeypatch.setattr(meter_mod, "STUCK", 1)

    class Quiet:
        def rsync_env(self):
            return dict(os.environ)
    sender = Sender(Quiet(), "b", "001")
    m = meter_mod.Meter(100)
    code, out, err, stuck = sender._live([sys.executable, "-c", "import time; time.sleep(60)"], m, 0, None)
    assert stuck and m.sent == 0
