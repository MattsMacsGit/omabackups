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
