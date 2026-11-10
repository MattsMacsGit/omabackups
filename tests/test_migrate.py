"""Migrate end to end on the fake server (6.1 F, D22a): an old computer's
backup; a new computer joins with the password, brings settings back (its
user name differs), and its first backup takes the backup over."""

import json
import shutil
import sys

import pytest
from fake_source import FakeSource
from gate_harness import GATE
from test_run import FAKE_SSH, world  # noqa: F401  (world: the fixture)

from omabackups.backup import run
from omabackups.core import ids, paths, rootjob
from omabackups.core.errors import OmaError
from omabackups.migrate import plan
from omabackups.setup import server as setup_server

HOST_KEYS = ["omabackups-server ssh-ed25519 AAAA"]
CHANGES = {"format": 1, "user": "u", "groups": [{"id": "settings", "title": "Settings"},
                                               {"id": "tweaks", "title": "System tweaks"}],
           "items": [
               {"id": "setting:app", "group": "settings", "name": "App", "suggest": "keep",
                "source": {"kind": "config", "refs": []}, "paths": ["~/.config/app"]},
               {"id": "tweak:thing", "group": "tweaks", "name": "Thing", "suggest": "keep",
                "source": {"kind": "file", "refs": []}, "paths": ["/etc/thing.conf"]},
               {"id": "setting:big", "group": "settings", "name": "Not this", "suggest": "leave",
                "source": {"kind": "config", "refs": []}, "paths": ["~/.config/big"]}]}


def old_computer_backs_up(world) -> str:
    srv, kid, bid, src, box = world
    for rel, data in {"home/u/.config/app/conf": "mine", "home/u/.config/big/x": "big",
                      "system/etc/thing.conf": "tweak"}.items():
        p = src.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
    point = run.backup(source=src)["point"]
    (box / "points" / point / "changes.json").write_text(json.dumps(CHANGES))
    return point


def become_a_new_computer(world, sandbox, monkeypatch) -> str:
    srv = world[0]
    (sandbox.sysroot / "etc/machine-id").write_text("1" * 32 + "\n")
    for folder in (paths.system_state_dir(), paths.system_config_dir(), paths.keys_dir()):
        shutil.rmtree(folder, ignore_errors=True)
    pub = setup_server.link()
    kid = json.loads(srv.gate("admin", "add-computer", ids.system_id(), "new", input=pub.encode()).stdout)["key"]
    monkeypatch.setenv("OMABACKUPS_TEST_GATE", f"{GATE}:{kid}")
    monkeypatch.setenv("OMABACKUPS_TEST_KEY", kid)
    monkeypatch.setenv("OMABACKUPS_TEST_RSH", f"{sys.executable} {FAKE_SSH}")
    return kid


def test_migrate_then_the_first_backup_takes_over(world, sandbox, monkeypatch, tmp_path):
    srv, kid, bid, src, box = world
    point = old_computer_backs_up(world)
    become_a_new_computer(world, sandbox, monkeypatch)

    with pytest.raises(OmaError):
        rootjob.run("migrate-join", {"address": "test", "host_keys": HOST_KEYS, "password": "wrong"})
    joined = rootjob.run("migrate-join", {"address": "test", "host_keys": HOST_KEYS, "password": "password1"})
    assert joined["backup"] == bid and point in joined["points"]
    assert json.loads(paths.server_file().read_text())["migrating"] is True

    changes = rootjob.run("migrate-info", {"point": point})["changes"]
    job = plan.jobs(changes, plan.suggested(changes))
    assert job["home"] == ["~/.config/app"] and job["system"] == ["/etc/thing.conf"]
    done = rootjob.run("migrate-settings", {"point": point, "from_user": "u", "home": job["home"],
                                            "system": job["system"], "units": []})
    assert done["problems"] == []
    assert (sandbox.home / ".config/app/conf").read_text() == "mine"          # into this user's home
    assert not (sandbox.home / ".config/big").exists()                        # not ticked
    assert (sandbox.sysroot / "etc/thing.conf").read_text() == "tweak"

    new_src = FakeSource(tmp_path / "new-computer")
    for rel, data in {"system/etc/hostname": "new", "home/u/notes.txt": "hello", "boot/vmlinuz": "k"}.items():
        p = new_src.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
    import os
    monkeypatch.setattr(run, "linked_user", lambda: "newu")        # a new user name here
    (new_src.root / "home/u").rename(new_src.root / "home/newu")
    shutil.copy2(src.root / "home/u/notes.txt", new_src.root / "home/newu/notes.txt")  # as restored: same date
    first = run.backup(source=new_src)["point"]
    assert (box / "points" / first / "home/newu/notes.txt").exists()
    assert not (box / "points" / first / "home/u").exists()
    assert run.load_record()["sent"]["home"].get("files_sent", 0) == 0   # renamed, not sent again
    assert first.startswith("002-")
    saved = json.loads(paths.server_file().read_text())
    assert saved["line"] == "002" and saved["migrating"] is False and saved["return_point"] == point
    lines = {e["line"]: e for e in json.loads((box / "lines.json").read_text())["lines"]}
    assert lines["001"]["read_only"] and lines["002"]["from"] == point
    assert run.backup(source=new_src)["point"].startswith("002-")                 # and it carries on
    from omabackups.commands import status_data
    listed = {p["name"]: p for p in status_data.points(run.load_record())}
    assert point in listed and listed[point]["return_point"]      # the old line stays reachable


def test_run_migrate_again_sees_whats_here_already(world, sandbox, monkeypatch):
    """D44: a dry run against the restore point, nothing copied: what came
    over is here; a part not brought, or changed since, isn't."""
    from omabackups.migrate import here
    old_history = "".join(f"old command {n}\n" for n in range(30))
    (world[3].root / "home/u").mkdir(parents=True, exist_ok=True)
    (world[3].root / "home/u/.bash_history").write_text(old_history)
    point = old_computer_backs_up(world)
    become_a_new_computer(world, sandbox, monkeypatch)
    rootjob.run("migrate-join", {"address": "test", "host_keys": HOST_KEYS, "password": "password1"})
    changes = rootjob.run("migrate-info", {"point": point})["changes"]
    job = plan.jobs(changes, plan.suggested(changes))
    rootjob.run("migrate-settings", {"point": point, "from_user": "u", "home": job["home"],
                                     "system": job["system"], "units": []})
    home, system = here.asked(changes)
    seen = rootjob.run("migrate-here", {"point": point, "from_user": "u", "home": home, "system": system})
    assert seen == {"home": [".config/app"], "system": ["etc/thing.conf"]}
    assert not (sandbox.home / ".config/big").exists()                   # a dry run: nothing copied
    assert here.found(changes, set(seen["home"]), set(seen["system"]), (set(), set())) == \
        {"setting:app", "tweak:thing"}
    (sandbox.home / ".config/app/conf").write_text("changed since, by you")
    again = rootjob.run("migrate-here", {"point": point, "from_user": "u", "home": home, "system": system})
    assert again["home"] == []
    # History: in when it has the past in it, however much was typed since.
    ask = {"point": point, "from_user": "u", "home": [".bash_history"], "system": []}
    history = sandbox.home / ".bash_history"
    history.write_text("typed on the new computer\n" * 40)
    assert rootjob.run("migrate-here", ask)["home"] == []                  # blank, then typed in
    history.write_text(old_history + "typed since\n" * 40)
    assert rootjob.run("migrate-here", ask)["home"] == [".bash_history"]   # came over, then grew
