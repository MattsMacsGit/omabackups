"""Setup's computer side against the fake server: link, the root job, create.
(SSH and the real encrypted box are tested on a real server: tests/live/server_check.py.)"""

import json
import os

import pytest
from gate_harness import GATE, FakeServer

from omabackups.core import flow, paths, rootjob, state
from omabackups.core.errors import OmaError
from omabackups.setup import bundle, server

HOST_KEY = "omabackups-server ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLE0"


@pytest.fixture
def world(sandbox, tmp_path, monkeypatch):
    """This computer, linked, with its key known to a fake server that has a store."""
    srv = FakeServer(tmp_path / "server")
    srv.init()
    monkeypatch.setenv("PKEXEC_UID", str(os.getuid()))
    monkeypatch.setenv("OMABACKUPS_GATE_ROOT", str(srv.root))
    pub = server.link()
    done = srv.gate("admin", "add-computer", "a" * 32, "test computer", input=pub.encode())
    kid = json.loads(done.stdout)["key"]
    monkeypatch.setenv("OMABACKUPS_TEST_GATE", f"{GATE}:{kid}")
    yield srv, kid
    srv.close()


def test_link_makes_root_keys_and_records_the_user(world):
    keys = paths.keys_dir()
    assert oct(keys.stat().st_mode & 0o777) == "0o700"
    assert oct((keys / "ssh_key").stat().st_mode & 0o777) == "0o600"
    assert oct((keys / "unlock_key").stat().st_mode & 0o777) == "0o600"
    assert json.loads(paths.linked_user_file().read_text())["uid"] == os.getuid()


def test_link_twice_keeps_the_same_key(world):
    first = (paths.keys_dir() / "ssh_key.pub").read_text()
    server.link()
    assert (paths.keys_dir() / "ssh_key.pub").read_text() == first


def test_create_sets_up_the_backup_and_the_next_step(world):
    srv, kid = world
    assert flow.where() is flow.Step.NOT_SET_UP
    made = server.create("testserver", [HOST_KEY], 2 << 30, "a good password")
    saved = json.loads(paths.server_file().read_text())
    assert saved["backup"] == made["backup"] and saved["address"] == "testserver"
    assert paths.known_hosts_file().read_text().strip() == HOST_KEY
    assert flow.where() is flow.Step.SETTING_UP
    # The backup on the server is locked again, and its password opens it.
    assert srv.ok(kid, "status")["backups"][0]["open"] is False
    srv.ok(kid, f"unlock {made['backup']}", b"a good password")


def test_a_refusal_from_the_server_is_plain_and_changes_nothing(world):
    srv, _ = world
    srv.env["OMABACKUPS_GATE_FAKE_FREE"] = str(1 << 30)
    with pytest.raises(OmaError) as caught:
        server.create("testserver", [HOST_KEY], 2 << 30, "a good password")
    assert "GiB free" in caught.value.what
    assert not paths.server_file().exists()
    assert state.read(flow.SETUP) is None          # still at "not set up"


def test_bad_requests_are_refused_by_the_root_job(world):
    for request in ({"address": "-oProxyCommand=x", "host_keys": [HOST_KEY], "size": 2 << 30, "password": "p"},
                    {"address": "srv", "host_keys": ["evil.com ssh-ed25519 AAAA"], "size": 2 << 30, "password": "p"},
                    {"address": "srv", "host_keys": [HOST_KEY], "size": 5, "password": "p"}):
        with pytest.raises(OmaError) as caught:
            rootjob.run("create-backup", request)
        assert caught.value.code == "bad-request"


def test_requests_from_another_user_are_refused(world):
    data = json.loads(paths.linked_user_file().read_text())
    paths.linked_user_file().write_text(json.dumps({**data, "uid": data["uid"] + 1}))
    with pytest.raises(OmaError):
        rootjob.run("create-backup", {})
    # Root refused it without reading it (so it can't vouch for it either).
    result = json.loads((paths.results_dir() / "create-backup.json").read_text())
    assert result["ok"] is False and result["error"]["code"] == "bad-request"
    assert not paths.server_file().exists()


def test_an_old_result_is_never_taken_for_a_new_one(world, monkeypatch):
    paths.results_dir().mkdir(parents=True, exist_ok=True)
    (paths.results_dir() / "create-backup.json").write_text(
        json.dumps({"ok": True, "answer": {"backup": "old"}, "nonce": "stale"}))
    monkeypatch.setattr(rootjob.subprocess, "run",
                        lambda *a, **k: rootjob.subprocess.CompletedProcess(a, 1, "", "boom"))
    with pytest.raises(OmaError) as caught:
        rootjob.run("create-backup", {})
    assert caught.value.code == "root-job-failed"


def test_setup_refuses_when_already_set_up(sandbox):
    state.write(flow.SETUP, {"where": "server", "first_backup": False})
    done = sandbox.run("setup", "server", "srv", "--login", "u", "--folder", "/x", "--size", "5")
    assert done.returncode == 1 and "already set up" in done.stderr


def test_the_gatekeeper_bundle_runs(sandbox, tmp_path):
    import subprocess
    import sys
    gate = bundle.gate_file()
    done = subprocess.run([sys.executable, str(gate), "version"], capture_output=True, text=True)
    assert json.loads(done.stdout) == {"gate": 1, "contract": 1}
    assert len(bundle.sha256(gate)) == 64


def test_store_path_must_be_full(sandbox):
    assert server.check_store("/srv/backups/omabackups/") == "/srv/backups/omabackups"
    for bad in ("relative/path", "/x\n/y"):
        with pytest.raises(OmaError):
            server.check_store(bad)


def test_link_writes_a_polkit_rule_for_this_user_only(world):
    import pwd
    rule = paths.polkit_rule_file().read_text()
    me = pwd.getpwuid(os.getuid()).pw_name
    assert f'subject.user !== "{me}"' in rule
    assert "omabackups-root@" in rule and "isInGroup" not in rule


def test_a_request_reached_through_a_link_is_refused(world, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    requests = paths.requests_dir()
    requests.mkdir(parents=True, exist_ok=True)
    requests.rmdir()
    requests.symlink_to(elsewhere)
    (elsewhere / "create-backup.json").write_text("{}")
    from omabackups.root import jobs
    with pytest.raises(OmaError) as caught:
        jobs.read_request("create-backup", os.getuid())
    assert caught.value.code == "no-request"
    assert (elsewhere / "create-backup.json").exists()   # never touched


def test_a_shared_request_folder_is_refused(world):
    requests = paths.requests_dir()
    requests.mkdir(parents=True, exist_ok=True)
    os.chmod(requests, 0o777)
    (requests / "create-backup.json").write_text("{}")
    from omabackups.root import jobs
    with pytest.raises(OmaError) as caught:
        jobs.read_request("create-backup", os.getuid())
    assert caught.value.code == "bad-request"


def test_the_cipher_is_named_right():
    from omabackups.commands.setup import cipher_name
    assert cipher_name("xchacha12,aes-adiantum-plain64").startswith("Adiantum")
    assert cipher_name("aes-xts-plain64") == "AES"
