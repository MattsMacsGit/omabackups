"""A whole backup run, through the fake server, with stand-in snapshots."""

import json
import sys
from pathlib import Path

import pytest
from fake_source import FakeSource
from gate_harness import GATE, FakeServer
from test_gate_data import tree

from omabackups.backup import run
from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.setup import server as setup_server

FAKE_SSH = Path(__file__).resolve().parent / "fake_ssh.py"


@pytest.fixture
def world(sandbox, tmp_path, monkeypatch):
    """A linked computer with its backup set up on a fake server."""
    srv = FakeServer(tmp_path / "server")
    srv.init()
    monkeypatch.setenv("PKEXEC_UID", "1000")
    pub = setup_server.link()
    kid = json.loads(srv.gate("admin", "add-computer", "a" * 32, "c", input=pub.encode()).stdout)["key"]
    for name, value in {**srv.env, "OMABACKUPS_TEST_GATE": f"{GATE}:{kid}", "OMABACKUPS_TEST_KEY": kid,
                        "OMABACKUPS_TEST_RSH": f"{sys.executable} {FAKE_SSH}"}.items():
        monkeypatch.setenv(name, value)
    setup_server.create("test", ["omabackups-server ssh-ed25519 AAAA"], 2 << 30, "password1")
    monkeypatch.setattr(run, "omarchy_version", lambda: "test")
    src = FakeSource(tmp_path / "computer")
    for rel, data in {"system/etc/hostname": "box", "home/u/notes.txt": "hello",
                      "home/u/.cache/junk": "j", "boot/vmlinuz": "kernel"}.items():
        p = src.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
    bid = json.loads(paths.server_file().read_text())["backup"]
    box = srv.root / "data/store" / f"{bid}.box" / "inside"
    yield srv, kid, bid, src, box
    srv.close()


def holds_left(srv, bid) -> list:
    folder = srv.root / "run/omabackups-gate/holds" / bid
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def latest(box: Path) -> Path:
    return box / "points" / sorted((box / "points").iterdir())[-1].name


def same(point: Path, src: FakeSource) -> None:
    for part in ("system", "boot"):
        assert tree(point / part) == tree(src.root / part), part
    home = {k: v for k, v in tree(src.root / "home").items() if ".cache" not in k}
    assert tree(point / "home") == home


def test_first_backup_is_full_then_quick(world, monkeypatch):
    srv, kid, bid, src, box = world
    first = run.backup(source=src)
    assert first["how"] == {"system": "full check", "home": "full check", "boot": "copied"}
    same(latest(box), src)
    info = json.loads((latest(box) / "point.json").read_text())
    assert info["owner"] and info["follows"] is None and info["skips"]["home"]

    (src.root / "home/u/notes.txt").write_text("changed")
    (src.root / "home/u/new.txt").write_text("new")
    (src.root / "system/etc/hostname").unlink()
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    second = run.backup(source=src)
    assert second["how"]["home"].startswith("changes (")
    assert second["how"]["system"].startswith("changes (")
    same(latest(box), src)
    # Only one snapshot per part stays on the computer.
    assert len([n for n in src.snapshots(None).names() if n.startswith("home-")]) == 1
    # It let go of its hold: the backup locks itself after the quiet time.
    assert holds_left(srv, bid) == []


def test_a_cut_off_backup_is_finished_by_the_next(world, monkeypatch):
    srv, kid, bid, src, box = world
    run.backup(source=src)
    (src.root / "home/u/new.txt").write_text("new")
    real = run.Sender.everyday

    def cut_off(self, *args):
        raise OmaError("network gone", code="send-failed")
    monkeypatch.setattr(run.Sender, "everyday", cut_off)
    with pytest.raises(OmaError):
        run.backup(source=src)
    assert run.load_record()["finished"] is False
    assert holds_left(srv, bid) == []      # let go even after a failure

    monkeypatch.setattr(run.Sender, "everyday", real)
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    again = run.backup(source=src)
    assert again["how"]["home"] == "full check"     # resumes with a full check
    same(latest(box), src)
    assert run.load_record()["finished"] is True


def test_a_changed_skip_list_means_a_full_check(world, monkeypatch):
    srv, kid, bid, src, box = world
    run.backup(source=src)
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    (paths.system_config_dir() / "skips.json").write_text(json.dumps({"home": ["notes.txt"]}))
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    again = run.backup(source=src)
    assert again["how"]["home"] == "full check"
    assert not (latest(box) / "home/u/notes.txt").exists()


def test_no_backup_location_is_explained(sandbox):
    with pytest.raises(OmaError) as caught:
        run.backup(source=None)
    assert caught.value.code == "not-set-up"
