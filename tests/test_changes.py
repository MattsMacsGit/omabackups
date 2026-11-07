"""The change list (btrfs's dump, written by hand here; the live check uses real ones)."""

import os

from omabackups.backup import changes
from omabackups.backup.skips import Skips

SKIPS = Skips([".cache", "/tmp"])


def dump(*lines: str) -> str:
    return "\n".join(["snapshot        ./new      uuid=a transid=10 parent_uuid=b parent_transid=8",
                      "utimes          ./new/     atime=1 mtime=1 ctime=1", *lines])


def make(snap, files: dict):
    for rel, content in files.items():
        p = snap / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content) if isinstance(content, bytes) else p.mkdir(exist_ok=True)


def test_a_renamed_folder_is_replayed_not_sent(tmp_path):
    make(tmp_path, {"Papers/a.txt": b"hello"})
    out = changes.plan(dump("rename          ./new/Documents   dest=./new/Papers",
                            "utimes          ./new/Papers      atime=1 mtime=2 ctime=2"),
                       "new", str(tmp_path), SKIPS)
    assert out.ops == [["rename", "Documents", "Papers"]]
    assert out.files == ["Papers"]          # only the folder's own details
    assert out.ranges == {}


def test_new_files_via_temporary_names(tmp_path):
    make(tmp_path, {"Papers/new.txt": b"new"})
    out = changes.plan(dump("mkfile          ./new/o261-10-0",
                            "rename          ./new/o261-10-0   dest=./new/Papers/new.txt",
                            "update_extent   ./new/Papers/new.txt   offset=0 len=3"),
                       "new", str(tmp_path), SKIPS)
    assert out.ops == []                     # the temporary name never reached the server
    assert out.files == ["Papers/new.txt"]


def test_deletes_are_replayed(tmp_path):
    out = changes.plan(dump("unlink          ./new/old.txt", "rmdir           ./new/olddir"),
                       "new", str(tmp_path), SKIPS)
    assert out.ops == [["delete", "old.txt"], ["delete", "olddir"]]


def test_names_with_spaces_and_escapes(tmp_path):
    make(tmp_path, {"My Files/ü x.txt": b"x"})
    out = changes.plan(dump(r"update_extent   ./new/My\ Files/\303\274\ x.txt   offset=0 len=1"),
                       "new", str(tmp_path), SKIPS)
    assert out.files == ["My Files/ü x.txt"]


def test_a_big_file_changed_a_little_goes_as_ranges(tmp_path, monkeypatch):
    monkeypatch.setattr(changes, "RANGES_FROM", 1000)
    make(tmp_path, {"vm.img": b"A" * 10_000, "small.img": b"B" * 10_000})
    out = changes.plan(dump("update_extent   ./new/vm.img   offset=4096 len=512",
                            "update_extent   ./new/vm.img   offset=4300 len=1000",
                            "update_extent   ./new/small.img   offset=0 len=9000"),
                       "new", str(tmp_path), SKIPS)
    assert out.ranges == {"vm.img": [(4096, 1204)]}     # overlapping ranges merged
    assert out.files == ["small.img"]                   # most of it changed: send it all


def test_new_big_files_go_whole(tmp_path, monkeypatch):
    monkeypatch.setattr(changes, "RANGES_FROM", 1000)
    make(tmp_path, {"vm.img": b"A" * 10_000})
    out = changes.plan(dump("mkfile          ./new/o300-10-0",
                            "rename          ./new/o300-10-0   dest=./new/vm.img",
                            "update_extent   ./new/vm.img   offset=0 len=100"),
                       "new", str(tmp_path), SKIPS)
    assert out.ranges == {} and out.files == ["vm.img"]


def test_skipped_places(tmp_path):
    make(tmp_path, {"keep/x": b"x", "keep/sub/y": b"y", "notes.txt": b"n"})
    out = changes.plan(dump(
        "update_extent   ./new/u/.cache/junk   offset=0 len=10",      # inside a skip: ignored
        "rename          ./new/notes-old.txt   dest=./new/u/.cache/notes-old.txt",  # moved in: delete
        "rename          ./new/u/.cache/keep   dest=./new/keep",      # moved out: send it all
        "update_extent   ./new/notes.txt   offset=0 len=1"),
        "new", str(tmp_path), SKIPS)
    assert ["delete", "notes-old.txt"] in out.ops
    assert not any(op[0] == "rename" for op in out.ops)
    assert set(out.files) == {"keep", "keep/x", "keep/sub", "keep/sub/y", "notes.txt"}


def test_changes_that_are_gone_again_are_left_out(tmp_path):
    out = changes.plan(dump("update_extent   ./new/vanished   offset=0 len=1"),
                       "new", str(tmp_path), SKIPS)
    assert out.files == []
    assert not os.path.exists(tmp_path / "vanished")
