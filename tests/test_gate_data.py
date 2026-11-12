"""The data verbs on the fake server, with real rsync through the relay."""

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from gate_harness import FakeServer, make_pubkey

KEY = b"K" * 64
FAKE_SSH = Path(__file__).resolve().parent / "fake_ssh.py"
BASE = ["-aHAX", "--numeric-ids"]


@pytest.fixture
def box(tmp_path):
    """An unlocked backup on the fake server; returns (server, key, backup, its line 001)."""
    srv = FakeServer(tmp_path / "server")
    srv.init()
    kid = srv.add_computer(1)
    bid = srv.create(kid)
    srv.ok(kid, f"unlock {bid}", KEY)
    yield srv, kid, bid, srv.root / "data/store" / f"{bid}.box" / "inside" / "current" / "001"
    srv.close()


def rsync(srv, kid, bid, part, src, *options, files_from=None):
    env = {**srv.env, "OMABACKUPS_TEST_KEY": kid}
    extra = [f"--files-from={files_from}", "--from0"] if files_from else []
    return subprocess.run(
        ["rsync", *BASE, *options, *extra, "-e", f"{sys.executable} {FAKE_SSH}",
         f"--rsync-path=send {bid} 001 {part}", f"{src}/", "omabackups-server:x/"],
        capture_output=True, text=True, env=env, timeout=60)


def tree(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            out[rel] = ("link", os.readlink(path))
        elif path.is_file():
            out[rel] = ("file", path.read_bytes())
        else:
            out[rel] = ("dir",)
    return out


def make_source(src: Path) -> None:
    (src / "Documents" / "deep").mkdir(parents=True)
    (src / "Documents" / "a.txt").write_text("hello")
    (src / "Documents" / "deep" / "b ü ñ.txt").write_text("unicode name")
    (src / "big.bin").write_bytes(os.urandom(300_000))
    (src / "link").symlink_to("Documents/a.txt")


def test_a_full_send_arrives_exactly(box, tmp_path):
    srv, kid, bid, line = box
    src = tmp_path / "src"
    make_source(src)
    done = rsync(srv, kid, bid, "home", src, "--delete", "--partial-dir=.rsync-partial")
    assert done.returncode == 0, done.stderr
    assert tree(line / "home") == tree(src)


def test_only_listed_files_are_sent(box, tmp_path):
    srv, kid, bid, line = box
    src = tmp_path / "src"
    make_source(src)
    assert rsync(srv, kid, bid, "home", src).returncode == 0
    (src / "Documents" / "a.txt").write_text("changed")
    (src / "Documents" / "deep" / "b ü ñ.txt").write_text("also changed but not listed")
    listing = tmp_path / "list"
    listing.write_bytes(b"Documents/a.txt\0")
    assert rsync(srv, kid, bid, "home", src, files_from=listing).returncode == 0
    assert (line / "home/Documents/a.txt").read_text() == "changed"
    assert (line / "home/Documents/deep/b ü ñ.txt").read_text() == "unicode name"


@pytest.mark.parametrize("bad", [
    ["--log-file=/etc/x"], ["--link-dest=/"], ["--temp-dir", "/tmp"], ["--backup-dir=/etc"],
    ["--remove-source-files"], ["--partial-dir", "/etc"], ["--sender"], ["--files-from=/etc/shadow"],
    ["-lHogDtprxe.iLsf;rm"], ["--rsync-path=x"],
    ["--log-format=%i;rm"], ["--log-format=/etc/x"], ["--log-format=%f %i"]])   # D49: only %i or X
def test_dangerous_rsync_options_are_refused(box, bad):
    srv, kid, bid, line = box
    words = " ".join(["--server", "-lHogDtpAXre.iLsfxCIvu", *bad, ".", "x/"])
    code, _, error = srv.call(kid, f"send {bid} 001 home {words}")
    assert code == 1, (bad, error)
    assert "not allowed" in error or "can't read" in error or "isn't an rsync" in error


def test_the_destination_is_always_the_gatekeepers_own(box, tmp_path):
    srv, kid, bid, line = box
    src = tmp_path / "src"
    make_source(src)
    env = {**srv.env, "OMABACKUPS_TEST_KEY": kid}
    done = subprocess.run(["rsync", *BASE, "-e", f"{sys.executable} {FAKE_SSH}",
                           f"--rsync-path=send {bid} 001 home", f"{src}/",
                           f"omabackups-server:{tmp_path}/elsewhere/"],
                          capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert not (tmp_path / "elsewhere").exists()
    assert (line / "home" / "big.bin").exists()


def test_send_only_into_the_three_parts_and_own_line(box, tmp_path):
    srv, kid, bid, line = box
    for command in (f"send {bid} 001 etc --server -le.x . x", f"send {bid} 002 home --server -le.x . x",
                    f"send {bid} 001 ../x --server -le.x . x"):
        code, _, error = srv.call(kid, command)
        assert code == 1, (command, error)


def test_a_rescue_key_cant_send(box, tmp_path):
    srv, kid, bid, line = box
    rescue = srv.ok(kid, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    src = tmp_path / "src"
    make_source(src)
    assert rsync(srv, rescue, bid, "home", src).returncode != 0
    assert not (line / "home" / "big.bin").exists()


def test_renames_and_deletes_are_replayed(box, tmp_path):
    srv, kid, bid, line = box
    src = tmp_path / "src"
    make_source(src)
    rsync(srv, kid, bid, "home", src)
    ops = [["rename", "Documents", "Papers"], ["delete", "big.bin"], ["delete", "not-there"]]
    assert srv.ok(kid, f"apply {bid} 001 home", json.dumps(ops).encode()) == {"applied": 2}
    assert (line / "home/Papers/a.txt").read_text() == "hello"
    assert not (line / "home/big.bin").exists()


def test_replay_never_leads_out_of_the_backup(box, tmp_path):
    srv, kid, bid, line = box
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious").write_text("keep me")
    (line / "home").mkdir(exist_ok=True)
    (line / "home" / "escape").symlink_to(outside)
    for ops in ([["delete", "escape/precious"]], [["rename", "escape/precious", "x"]],
                [["delete", "../../../x"]], [["delete", "/etc/passwd"]]):
        code, _, error = srv.call(kid, f"apply {bid} 001 home", json.dumps(ops).encode())
        assert code == 1, ops
    assert (outside / "precious").read_text() == "keep me"
    # Deleting the link itself is fine: it removes the link, not what it points to.
    srv.ok(kid, f"apply {bid} 001 home", json.dumps([["delete", "escape"]]).encode())
    assert (outside / "precious").exists()


def test_changed_ranges_are_written_in_place(box, tmp_path):
    srv, kid, bid, line = box
    (line / "home").mkdir(exist_ok=True)
    target = line / "home" / "vm.img"
    target.write_bytes(b"A" * 100_000)
    data = json.dumps({"path": "vm.img", "size": 100_010}).encode() + b"\n"
    for offset, chunk in ((10, b"BBBB"), (99_000, b"C" * 1010)):
        data += struct.pack(">QQ", offset, len(chunk)) + chunk
    assert srv.ok(kid, f"ranges {bid} 001 home", data) == {"written": 1014}
    content = target.read_bytes()
    assert len(content) == 100_010 and content[10:14] == b"BBBB" and content[-5:] == b"CCCCC"
    assert content[:10] == b"A" * 10


def test_restore_points_and_kept_ones(box, tmp_path):
    srv, kid, bid, line = box
    (line / "home").mkdir(exist_ok=True)
    (line / "home" / "f").write_text("v1")
    point = json.dumps({"owner": "a" * 32}).encode()
    srv.ok(kid, f"snapshot {bid} 001 001-2026-11-07-1000", point)
    (line / "home" / "f").write_text("v2")
    srv.ok(kid, f"snapshot {bid} 001 001-2026-11-07-1100", point)
    inside = line.parent.parent
    assert (inside / "points/001-2026-11-07-1000/home/f").read_text() == "v1"
    assert "newer" in srv.call(kid, f"snapshot {bid} 001 001-2026-11-07-0900", point)[2]
    assert "this line" in srv.call(kid, f"snapshot {bid} 001 002-2026-11-08-0900", point)[2]
    assert srv.ok(kid, f"keep {bid} 001-2026-11-07-1000") == {"kept": ["001-2026-11-07-1000"]}
    srv.ok(kid, f"snapshot {bid} 001 001-2026-11-07-1200", point)
    assert "kept" in srv.call(kid, f"delete {bid} 001-2026-11-07-1000")[2]
    srv.ok(kid, f"release {bid} 001-2026-11-07-1000")
    srv.ok(kid, f"delete {bid} 001-2026-11-07-1000")
    assert srv.ok(kid, f"points {bid}")["points"] == ["001-2026-11-07-1100", "001-2026-11-07-1200"]


def test_fetch_reads_a_restore_point_back(box, tmp_path):
    srv, kid, bid, line = box
    src = tmp_path / "src"
    make_source(src)
    assert rsync(srv, kid, bid, "home", src).returncode == 0
    srv.ok(kid, f"snapshot {bid} 001 001-2026-11-07-1000", b"{}")
    rescue = srv.ok(kid, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    back = tmp_path / "back"
    env = {**srv.env, "OMABACKUPS_TEST_KEY": rescue}
    done = subprocess.run(["rsync", *BASE, "-e", f"{sys.executable} {FAKE_SSH}",
                           f"--rsync-path=fetch {bid} 001-2026-11-07-1000 home",
                           "omabackups-server:x/", f"{back}/"],
                          capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert tree(back) == tree(src)


def test_fetch_never_writes_and_stays_in_points(box):
    srv, kid, bid, line = box
    srv.ok(kid, f"snapshot {bid} 001 001-2026-11-07-1000", b"{}")
    for command in (f"fetch {bid} 001-2026-11-07-1000 home --server -le.x . x",       # not a sender
                    f"fetch {bid} ../current home --server --sender -le.x . x",
                    f"fetch {bid} 001-2026-11-07-1000 etc --server --sender -le.x . x"):
        code, _, error = srv.call(kid, command)
        assert code == 1, (command, error)


def test_reuse_clones_only_what_is_unchanged(box, tmp_path):
    srv, kid, bid, line = box
    home = line / "home"
    (home / "Videos").mkdir(parents=True)
    (home / "Videos" / "big.mkv").write_bytes(b"V" * 1000)
    (home / "restored.iso").write_bytes(b"I" * 500)
    (home / "edited.txt").write_text("old")
    srv.ok(kid, f"snapshot {bid} 001 001-2026-11-01-1000", b"{}")
    point = line.parent.parent / "points" / "001-2026-11-01-1000" / "home"
    iso, edited = (point / "restored.iso").stat(), (point / "edited.txt").stat()
    for name in ("Videos", "restored.iso", "edited.txt"):          # gone from the working copy
        p = home / name
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    asked = {"dirs": ["Videos", "NotThere"],
             "files": [["restored.iso", iso.st_size, iso.st_mtime_ns],
                       ["edited.txt", edited.st_size, edited.st_mtime_ns + 1]]}   # a different date
    done = srv.ok(kid, f"reuse {bid} 001 home", json.dumps(asked).encode())
    assert done == {"dirs": 1, "files": 1, "bytes": 1500}       # the folder (1000) + the file (500)
    assert (home / "Videos" / "big.mkv").read_bytes() == b"V" * 1000
    assert (home / "restored.iso").exists() and not (home / "edited.txt").exists()


def test_reuse_stays_inside(box):
    srv, kid, bid, line = box
    for asked in ({"dirs": ["../../points"]}, {"files": [["/etc/passwd", 1, 1]]}):
        assert srv.call(kid, f"reuse {bid} 001 home", json.dumps(asked).encode())[0] == 1


def test_reuse_finds_a_file_under_the_old_user_name(box):
    """A Migrate with a new user name, then Restore my files: the server had the
    file all along under the old name; it's cloned, not sent again (gate 14)."""
    srv, kid, bid, line = box
    home = line / "home"
    (home / "old/Documents").mkdir(parents=True)
    (home / "old/Documents/report.pdf").write_bytes(b"R" * 700)
    srv.ok(kid, f"snapshot {bid} 001 001-2026-11-01-1000", b"{}")
    was = (line.parent.parent / "points/001-2026-11-01-1000/home/old/Documents/report.pdf").stat()
    asked = {"files": [["new/Documents/report.pdf", was.st_size, was.st_mtime_ns, "old/Documents/report.pdf"]]}
    assert srv.ok(kid, f"reuse {bid} 001 home", json.dumps(asked).encode())["files"] == 1
    assert (home / "new/Documents/report.pdf").read_bytes() == b"R" * 700
    for bad in ("../../points/x", "/etc/passwd"):                    # the old name stays inside too
        asked = {"files": [["new/x", 1, 1, bad]]}
        assert srv.call(kid, f"reuse {bid} 001 home", json.dumps(asked).encode())[0] in (0, 1)
        assert not (home / "new/x").exists()
