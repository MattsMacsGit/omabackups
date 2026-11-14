"""Sending a part through the fake server: full, then everyday (the mix)."""

import os
import sys
from pathlib import Path

import pytest
from gate_harness import GATE, FakeServer
from test_gate_data import tree

from omabackups.backup.changes import Plan
from omabackups.backup.send import Sender
from omabackups.backup.skips import Skips
from omabackups.core.errors import OmaError
from omabackups.where.server import Gate

FAKE_SSH = Path(__file__).resolve().parent / "fake_ssh.py"


@pytest.fixture
def sender(sandbox, tmp_path, monkeypatch):
    srv = FakeServer(tmp_path / "server")
    srv.init()
    kid = srv.add_computer(1)
    bid = srv.create(kid)
    srv.ok(kid, f"unlock {bid}", b"K" * 64)
    for name, value in {**srv.env, "OMABACKUPS_TEST_GATE": f"{GATE}:{kid}",
                        "OMABACKUPS_TEST_KEY": kid,
                        "OMABACKUPS_TEST_RSH": f"{sys.executable} {FAKE_SSH}"}.items():
        monkeypatch.setenv(name, value)
    line = srv.root / "data/store" / f"{bid}.box" / "inside" / "current" / "001"
    yield Sender(Gate("test"), bid, "001"), line
    srv.close()


def source(root: Path) -> Path:
    for rel, data in {"Documents/a.txt": b"hello", "Documents/deep/b.txt": b"b",
                      "vm.img": b"A" * 200_000, ".cache/junk": b"j"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    return root


def without(t: dict, prefix: str) -> dict:
    return {k: v for k, v in t.items() if not k.startswith(prefix)}


def test_full_then_everyday_ends_identical(sender, tmp_path):
    send, line = sender
    src = source(tmp_path / "src")
    send.full("home", str(src), Skips([".cache"]))
    assert tree(line / "home") == without(tree(src), ".cache")

    # A day's work: a folder renamed, a few bytes of the big file, a new file.
    os.rename(src / "Documents", src / "Papers")
    with open(src / "vm.img", "r+b") as f:
        f.seek(100_000)
        f.write(b"CHANGED")
    (src / "Papers" / "new.txt").write_text("new")
    plan = Plan(ops=[["rename", "Documents", "Papers"]], files=["Papers", "Papers/new.txt"],
                ranges={"vm.img": [(100_000, 7)]})
    send.everyday("home", str(src), plan)
    assert tree(line / "home") == without(tree(src), ".cache")
    sent = line / "home" / "vm.img"
    assert sent.stat().st_mtime_ns == (src / "vm.img").stat().st_mtime_ns
    assert oct(sent.stat().st_mode) == oct((src / "vm.img").stat().st_mode)


def test_newly_skipped_things_leave_the_working_copy_on_a_full_backup(sender, tmp_path):
    send, line = sender
    src = source(tmp_path / "src")
    send.full("home", str(src), Skips([]))
    assert (line / "home/.cache/junk").exists()
    send.full("home", str(src), Skips([".cache"]))
    assert not (line / "home/.cache").exists()


def test_a_failed_send_says_so(sender, tmp_path):
    send, line = sender
    with pytest.raises(OmaError) as caught:
        send.full("home", str(tmp_path / "does-not-exist"), Skips([]))
    assert caught.value.code == "send-failed" and "Resume backup" in caught.value.todo
