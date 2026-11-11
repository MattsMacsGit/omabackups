"""Restore my files (D37): the home folder comes back from a restore point,
and a file that's newer here is never overwritten."""

import os
import time

from test_run import world  # noqa: F401  (the fixture)

from omabackups.backup import run
from omabackups.restore import files


def test_a_deleted_folder_comes_back_and_newer_files_are_kept(world):
    srv, kid, bid, src, box = world
    home = src.root / "home" / "u"
    (home / "Projects/site").mkdir(parents=True)
    (home / "Projects/site/index.html").write_text("<h1>hi</h1>")
    (home / "notes.txt").write_text("old notes")
    point = run.backup(source=src)["point"]

    import shutil
    shutil.rmtree(home / "Projects")                       # deleted by mistake
    (home / "notes.txt").write_text("newer notes")         # changed since
    later = time.time() + 60
    os.utime(home / "notes.txt", (later, later))

    state = files.restore(point, "u", home=home)
    assert state.get("done"), (state.get("error") or {}).get("details")
    assert (home / "Projects/site/index.html").read_text() == "<h1>hi</h1>"
    assert (home / "notes.txt").read_text() == "newer notes"
    assert files.current()["done"]


def test_only_this_users_home_comes_back(world):
    srv, kid, bid, src, box = world
    other = src.root / "home" / "someone"
    other.mkdir(parents=True, exist_ok=True)
    (other / "theirs.txt").write_text("not yours")
    point = run.backup(source=src)["point"]
    import shutil
    shutil.rmtree(other)
    files.restore(point, "u", home=src.root / "home" / "u")
    assert not other.exists()


def test_picked_folders_come_back_whole_under_a_new_user_name(world, tmp_path):
    """Stage 8's failed check: a new user name, folders picked in Migrate.
    Every file inside must arrive (not just empty folders), then it's done."""
    srv, kid, bid, src, box = world
    old = src.root / "home" / "u"
    for rel in ("Documents/letters/one.txt", "Documents/two.txt", "Pictures/cat.jpg", "Work/plan.md"):
        (old / rel).parent.mkdir(parents=True, exist_ok=True)
        (old / rel).write_text(rel)
    point = run.backup(source=src)["point"]
    new_home = tmp_path / "newhome"                     # testrig02, say
    new_home.mkdir()
    state = files.restore(point, "newu", home=new_home, from_user="u", only=["Documents", "Pictures"])
    assert state.get("done"), (state.get("error") or {}).get("details")
    assert (new_home / "Documents/letters/one.txt").read_text() == "Documents/letters/one.txt"
    assert (new_home / "Pictures/cat.jpg").exists()
    assert not (new_home / "Work").exists()             # not picked


def test_a_restore_that_left_files_behind_is_never_done(world, tmp_path, monkeypatch):
    srv, kid, bid, src, box = world
    (src.root / "home/u/Documents").mkdir(parents=True, exist_ok=True)
    (src.root / "home/u/Documents/a.txt").write_text("a")
    point = run.backup(source=src)["point"]
    monkeypatch.setattr(files, "still_missing", lambda *a, **k: 3)
    state = files.restore(point, "u", home=tmp_path / "h", only=["Documents"])
    assert not state.get("done") and state["error"]["code"] == "restore-incomplete"
    assert "3 of your files" in state["error"]["what"]


def test_folders_already_here_are_named_before_old_files_are_mixed_in(tmp_path):
    from omabackups.restore.files import already_here
    (tmp_path / "src/clone").mkdir(parents=True)
    (tmp_path / "Documents").mkdir()                 # empty, as a fresh install makes it
    assert already_here(tmp_path, ["src", "Documents", "Music"]) == ["src"]


def test_a_network_drop_mid_restore_says_so_and_carries_on_next_time(world, tmp_path, monkeypatch):
    """Stage 10: the connection goes mid-copy. The user is told what happened
    and what to do; run again, it brings back what's still missing."""
    srv, kid, bid, src, box = world
    (src.root / "home/u/Documents").mkdir(parents=True, exist_ok=True)
    for n in range(5):
        (src.root / f"home/u/Documents/{n}.txt").write_text(str(n))
    point = run.backup(source=src)["point"]
    home = tmp_path / "h"
    monkeypatch.setenv("OMABACKUPS_TEST_RSH", "false")             # the line drops: ssh fails
    state = files.restore(point, "u", home=home)
    assert not state.get("done") and state["error"]["code"] == "restore-failed"
    assert "again" in state["error"]["todo"] and state["error"]["what"]
    from test_run import FAKE_SSH
    import sys
    monkeypatch.setenv("OMABACKUPS_TEST_RSH", f"{sys.executable} {FAKE_SSH}")   # back again
    again = files.restore(point, "u", home=home)
    assert again.get("done") and sorted(p.name for p in (home / "Documents").iterdir()) == \
        [f"{n}.txt" for n in range(5)]
