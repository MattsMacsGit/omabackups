"""A whole backup run, through the fake server, with stand-in snapshots."""

import json
import os
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
    monkeypatch.setenv("PKEXEC_UID", str(os.getuid()))
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
    assert first["how"] == {"system": "full, checked once", "home": "full, checked once", "boot": "copied"}
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
    assert again["how"]["home"] == "full, checked once"     # an everyday cut off: checked once
    same(latest(box), src)
    assert run.load_record()["finished"] is True


def test_a_changed_skip_list_means_a_full_check(world, monkeypatch):
    srv, kid, bid, src, box = world
    run.backup(source=src)
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    (paths.system_config_dir() / "skips.json").write_text(json.dumps({"home": ["notes.txt"]}))
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    again = run.backup(source=src)
    assert again["how"]["home"] == "full, checked once"
    assert not (latest(box) / "home/u/notes.txt").exists()


def test_no_backup_location_is_explained(sandbox):
    with pytest.raises(OmaError) as caught:
        run.backup(source=None)
    assert caught.value.code == "not-set-up"


def test_thinning_runs_after_a_backup(world, monkeypatch):
    srv, kid, bid, src, box = world
    points = box / "points"
    points.mkdir(exist_ok=True)
    old = ["001-2020-01-01-1000", "001-2020-01-01-1100", "001-2020-01-02-1000"]
    for name in old:
        (points / name).mkdir()
        (points / name / "point.json").write_text("{}")
    result = run.backup(source=src)
    names = sorted(p.name for p in points.iterdir())
    assert "001-2020-01-01-1000" not in names       # same week as 01-01-1100 and 01-02-1000
    assert result["point"] in names
    assert run.load_record()["thinned"]


def away_setup(monkeypatch, limit_mb=500):
    server = json.loads(paths.server_file().read_text())
    server["away"] = ["backup-server.away.test"]
    paths.server_file().write_text(json.dumps(server))
    monkeypatch.setenv("OMABACKUPS_TEST_REACHABLE", "backup-server.away.test")   # home address doesn't answer
    # The test gatekeeper runs on this computer: what it says about "its" addresses
    # is this computer's own. These tests are about the limit, not learning (D48).
    from omabackups.where import network
    monkeypatch.setattr(network, "learn_addresses", lambda gate, server: None)
    from omabackups.core import config
    values = config.load()
    values["away.limit_mb"] = limit_mb
    config.save(values)


def test_away_a_full_backup_over_the_limit_waits_for_an_answer(world, monkeypatch):
    """D49: the check knows a full backup's size, so the away limit applies to
    it like any other (it used to wait whenever the size wasn't known)."""
    srv, kid, bid, src, box = world
    away_setup(monkeypatch, limit_mb=0)
    from omabackups.backup.check import AwayWait
    with pytest.raises(AwayWait) as caught:
        run.backup(source=src)
    assert caught.value.size and caught.value.size > 0
    assert not (box / "points").exists() or not list((box / "points").iterdir())
    assert run.load_record().get("finished") is not False      # nothing half done
    done = run.backup(source=src, anyway=True)                 # "Back up now"
    assert done["away"] is True
    same(latest(box), src)


def test_away_small_changes_go_compressed_big_ones_wait(world, monkeypatch):
    srv, kid, bid, src, box = world
    run.backup(source=src)                                      # at home
    away_setup(monkeypatch, limit_mb=1)
    (src.root / "home/u/small.txt").write_text("small")
    monkeypatch.setattr(run, "point_name", lambda line, latest: f"{line}-2099-01-01-0000")
    sent = []
    real = run.Sender.__init__

    def spy(self, *a, **k):
        sent.append(k.get("compress"))
        real(self, *a, **k)
    monkeypatch.setattr(run.Sender, "__init__", spy)
    assert run.backup(source=src)["away"] is True and sent[-1] is True
    same(latest(box), src)

    (src.root / "home/u/big.bin").write_bytes(b"x" * 2_000_000)
    from omabackups.backup.check import AwayWait
    with pytest.raises(AwayWait) as caught:
        run.backup(source=src)
    assert caught.value.size >= 2_000_000


def test_unreachable_says_so(world, monkeypatch):
    monkeypatch.setenv("OMABACKUPS_TEST_REACHABLE", "nothing")
    with pytest.raises(OmaError) as caught:
        run.backup(source=world[3])
    assert caught.value.code == "unreachable"


def test_a_backup_that_doesnt_fit_thins_then_says_full(world, monkeypatch):
    srv, kid, bid, src, box = world
    run.backup(source=src)
    points = box / "points"
    for name in ("001-2020-01-01-1000", "001-2020-02-01-1000"):
        (points / name).mkdir()
    (src.root / "home/u/big.bin").write_bytes(b"x" * 100_000)
    srv.env["OMABACKUPS_GATE_FAKE_INSIDE_FREE"] = "1000"
    monkeypatch.setattr(run.check.time, "sleep", lambda s: None)
    with pytest.raises(OmaError) as caught:
        run.backup(source=src)
    assert caught.value.code == "backup-full"
    left = sorted(p.name for p in points.iterdir())
    assert "001-2020-01-01-1000" not in left and "001-2020-02-01-1000" not in left
    assert len(left) == 1          # the newest stays, always


def test_nested_subvolumes_are_reported_not_hidden(world, sandbox):
    srv, kid, bid, src, box = world
    src.list[1].nested_for_test = ["u/vms", "u/.cache/x"]        # the second one is skipped anyway
    run.backup(source=src)
    assert run.load_record()["not_included"] == [f"{src.root}/home/u/vms"]
    assert json.loads((latest(box) / "point.json").read_text())["not_included"]
    done = sandbox.run("status")
    assert "Some folders aren't backed up" in done.stdout and "u/vms" in done.stdout


def test_health_is_due_once_a_night_at_its_hour():
    from datetime import datetime

    from omabackups.backup import health
    from omabackups.core import config
    s = config.defaults()          # on, at 0:00
    night = datetime(2026, 11, 8, 0, 5)
    assert health.due(s, None, night)
    assert not health.due(s, int(datetime(2026, 11, 8, 0, 1).timestamp()), night)   # already tonight
    assert health.due(s, int(datetime(2026, 11, 7, 0, 1).timestamp()), night)       # last night's
    assert not health.due(s, None, datetime(2026, 11, 8, 3, 0))                      # not its hour
    assert not health.due({**s, "health.on": False}, None, night)


def test_damage_found_means_one_full_checksum_backup(world, monkeypatch):
    srv, kid, bid, src, box = world
    run.backup(source=src)
    from omabackups.root import keys
    hold = srv.ok(kid, f"unlock {bid}", keys.read_unlock_key())["hold"]     # this computer's real key
    srv.ok(kid, f"health-start {bid} 60")
    scrub = srv.root / "run/omabackups-gate" / f"fake-scrub-{bid}.json"
    scrub.write_text(json.dumps({"status": "finished", "csum_errors": 1}))
    srv.ok(kid, f"lock {bid} {hold}")
    names = iter(f"001-2099-01-0{i}-0000" for i in range(1, 9))
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    second = run.backup(source=src)
    assert second["how"]["home"] == "full check, every file's contents"
    third = run.backup(source=src)
    assert third["how"]["home"].startswith("changes (")      # answered once, then quick again


def test_boot_counts_only_what_changed(world):
    srv, kid, bid, src, box = world
    from omabackups.backup import check
    size, manifest = check.folder_changes(str(src.root / "boot"), {})
    assert size == len("kernel")
    again, _ = check.folder_changes(str(src.root / "boot"), manifest)
    assert again == 0


def test_the_hold_is_kept_alive_during_a_long_part(world, monkeypatch):
    srv, kid, bid, src, box = world
    monkeypatch.setattr(run.HoldKeeper, "EVERY", 0.2)
    real = run.Sender.copy             # a full backup's home goes as its checked list (D49)
    seen = []

    def slow(self, part, *args, **kwargs):
        if part == "home":
            import time
            folder = srv.root / "run/omabackups-gate/holds" / bid
            hold = next(folder.iterdir())
            os.utime(hold, (0, 0))                 # as if 10+ minutes had passed...
            time.sleep(1)                          # ...the keeper refreshes it meanwhile
            seen.append(hold.stat().st_mtime > 1000)
        return real(self, part, *args, **kwargs)
    monkeypatch.setattr(run.Sender, "copy", slow)
    run.backup(source=src)
    assert seen == [True]


@pytest.mark.real_audit
def test_every_restore_point_carries_its_changes(world, sandbox):
    srv, kid, bid, src, box = world
    result = run.backup(source=src)
    changes = json.loads((latest(box) / "changes.json").read_text())
    assert changes["format"] == 1 and changes["source"]["system"] == "omarchy"
    info = srv.ok(kid, f"info {bid} {result['point']}")
    assert info["changes"]["made"] == changes["made"] and info["point"]["owner"]
    shown = sandbox.run("changes")
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout.startswith("Your changes to Omarchy\nLatest backup was ")


def test_no_changes_list_yet_is_explained(sandbox):
    done = sandbox.run("changes")
    assert done.returncode == 1 and "back up once" in done.stderr


def test_keep_release_and_the_password(world, sandbox, monkeypatch):
    srv, kid, bid, src, box = world
    point = run.backup(source=src)["point"]
    from omabackups.core import rootjob
    rootjob.run("keep", {"point": point, "keep": True})
    assert run.load_record()["kept"] == [point]
    assert "★ kept" in sandbox.run("points").stdout
    rootjob.run("keep", {"point": point, "keep": False})
    assert run.load_record()["kept"] == []
    import pytest as _pytest
    with _pytest.raises(OmaError):
        rootjob.run("change-password", {"old": "wrong", "new": "a new password"})
    rootjob.run("change-password", {"old": "password1", "new": "a new password"})
    assert srv.call(kid, f"unlock {bid}", b"password1")[0] == 1
    srv.ok(kid, f"unlock {bid}", b"a new password")


def test_d29_automatic_backups_wait_for_a_back_up_now(world, sandbox):
    srv, kid, bid, src, box = world
    assert run.load_record().get("automatic_paused") is True          # a fresh setup
    run.backup(source=src, manual=False)
    assert run.load_record()["automatic_paused"] is True              # automatic ones don't end it
    run.backup(source=src)                                            # a Back up now
    assert run.load_record()["automatic_paused"] is False
    from omabackups.root import job_skips
    job_skips.set_skips({"skips": {"home": []}})                      # the picker saved
    assert run.load_record()["automatic_paused"] is True
    done = sandbox.run("--json", "status")
    assert "automatic-off" in done.stdout
