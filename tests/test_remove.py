"""Remove OmaBackups (audit 10.2): services, snapshots and settings go; the
backup only when asked twice, and only by its owner."""

import io
import json
import sys
from types import SimpleNamespace

import pytest
from gate_harness import make_pubkey
from test_gate import KEY, owned, server  # noqa: F401  (fixtures)
from test_run import world  # noqa: F401  (the fixture)

from omabackups.backup import run
from omabackups.commands import remove as remove_cmd
from omabackups.core import paths, rootjob
from omabackups.core.errors import OmaError
from omabackups.core.events import Events
from omabackups.root import jobs


def test_only_the_owner_destroys_and_the_sticks_key_goes_too(owned):  # noqa: F811
    server, kid, bid = owned
    rescue = server.ok(kid, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    assert server.call(rescue, f"destroy {bid}")[0] == 1
    other = server.add_computer(2)
    assert server.call(other, f"destroy {bid}")[0] == 1
    box = server.root / "data/store" / f"{bid}.box"
    assert box.exists()
    assert server.ok(kid, f"destroy {bid}") == {"destroyed": bid}
    assert not box.exists() and server.ok(kid, "status")["backups"] == []
    assert "isn't known" in server.call(rescue, "status")[2]


def test_remove_keeps_the_backup_unless_asked(world):  # noqa: F811
    srv, kid, bid, src, box = world
    run.backup(source=src)
    rule = paths.polkit_rule_file()
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text("// rule")
    assert jobs._jobs()["remove"]({"delete_backup": False}) == {"removed": True, "destroyed": False}
    assert not paths.system_state_dir().exists() and not paths.system_config_dir().exists()
    assert not rule.exists()
    assert box.exists()                                       # your backup stays


def test_remove_and_delete_the_backup(world):  # noqa: F811
    srv, kid, bid, src, box = world
    run.backup(source=src)
    assert jobs._jobs()["remove"]({"delete_backup": True})["destroyed"] is True
    assert not box.exists()


def test_it_asks_twice_before_deleting_the_backup(sandbox, monkeypatch):
    paths.server_file().parent.mkdir(parents=True, exist_ok=True)
    paths.server_file().write_text(json.dumps({"kind": "server"}))
    asked = []
    monkeypatch.setattr(rootjob, "run", lambda job, request: asked.append(request) or {"destroyed": False})
    for answers, wanted in (("y\nn\n", False), ("y\ny\nn\n", False), ("y\ny\ny\n", True)):
        monkeypatch.setattr(sys, "stdin", io.StringIO(answers))
        remove_cmd.run_remove(SimpleNamespace(), Events())
        assert asked[-1] == {"delete_backup": wanted}
    monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))
    with pytest.raises(OmaError):                             # Cancel: nothing at all
        remove_cmd.run_remove(SimpleNamespace(), Events())
    assert len(asked) == 3
