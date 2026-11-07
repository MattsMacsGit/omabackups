"""A backup disk on this computer: the local gatekeeper (same code as a server's)."""

import json
import os

import pytest
from fake_source import FakeSource
from test_gate_data import tree
from test_run import latest, same

from omabackups.backup import run
from omabackups.core import flow, paths, rootjob, state
from omabackups.core.errors import OmaError
from omabackups.setup import server as setup_server


@pytest.fixture
def disk(sandbox, tmp_path, monkeypatch):
    monkeypatch.setenv("PKEXEC_UID", str(os.getuid()))
    monkeypatch.setenv("OMABACKUPS_GATE_ROOT", str(tmp_path / "local"))
    monkeypatch.setattr(run, "omarchy_version", lambda: "test")
    setup_server.link()
    device = tmp_path / "usb-disk"
    made = rootjob.run("create-disk", {"device": str(device), "size": 32 << 30, "model": "Test",
                                       "password": "a good password"})
    state.write(flow.SETUP, {"where": "disk", "first_backup": False})
    src = FakeSource(tmp_path / "computer")
    for rel, data in {"system/etc/hostname": "box", "home/u/notes.txt": "hello",
                      "boot/vmlinuz": "kernel"}.items():
        (src.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (src.root / rel).write_text(data)
    return made, device / "part1" / "inside", src


def test_set_up_and_back_up_to_a_disk(disk, monkeypatch):
    made, box, src = disk
    saved = json.loads(paths.server_file().read_text())
    assert saved["kind"] == "disk" and saved["backup"] == made["backup"]
    assert flow.where() is flow.Step.SETTING_UP

    first = run.backup(source=src)
    assert first["how"]["home"] == "full check" and first["away"] is False
    same(latest(box), src)
    assert flow.where() is flow.Step.EVERYDAY
    from omabackups.commands import status_data
    assert status_data.build()["header"]["where"] == "your backup disk (Test)"

    (src.root / "home/u/new.txt").write_text("new")
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    second = run.backup(source=src)
    assert second["how"]["home"].startswith("changes (")
    same(latest(box), src)


def test_a_disk_that_isnt_plugged_in_says_so(disk):
    made, box, src = disk
    saved = json.loads(paths.server_file().read_text())
    saved["device"] = "/dev/disk/by-partuuid/not-here"
    paths.server_file().write_text(json.dumps(saved))
    with pytest.raises(OmaError) as caught:
        run.backup(source=src)
    assert caught.value.code == "unreachable" and "plugged in" in caught.value.what


def test_start_over_forgets_but_keeps_the_backup(disk, sandbox):
    made, box, src = disk
    run.backup(source=src)
    before = tree(box)
    done = sandbox.run("start-over")
    assert done.returncode == 0, done.stderr
    assert "still there on the backup disk" in done.stdout
    assert flow.where() is flow.Step.NOT_SET_UP
    assert not paths.server_file().exists()
    assert tree(box) == before          # D28: nothing in the backup was deleted
