"""The gatekeeper on the fake server: roles, create, unlock/lock, refusals."""

import json
import os

import pytest
from gate_harness import FakeServer, make_pubkey

KEY = b"K" * 64


@pytest.fixture
def server(tmp_path):
    srv = FakeServer(tmp_path / "server")
    yield srv
    srv.close()


@pytest.fixture
def owned(server):
    """A server with one computer and its backup."""
    server.init()
    kid = server.add_computer(1)
    return server, kid, server.create(kid)


def test_version(server):
    server.init()
    kid = server.add_computer(1)
    assert server.ok(kid, "version") == {"gate": 5, "contract": 1}


def test_unknown_keys_and_verbs_are_refused(server):
    server.init()
    kid = server.add_computer(1)
    code, _, error = server.call("0" * 16, "status")
    assert code == 1 and "isn't known" in error
    code, _, error = server.call(kid, "rm -rf /")
    assert code == 2 and "unknown request" in error
    code, _, error = server.call(kid, "")
    assert code == 2


def test_authorized_keys_only_reach_the_relay(server):
    server.init()
    kid = server.add_computer(1)
    keys = (server.root / "var/lib/omabackups-gate/home/.ssh/authorized_keys").read_text()
    line = [x for x in keys.splitlines() if kid in x][0]
    assert line.startswith(f'restrict,command="/usr/bin/python3 /usr/lib/omabackups-gate/gate.pyz client {kid}"')


def test_create_makes_a_finished_locked_box(owned):
    server, kid, bid = owned
    status = server.ok(kid, "status")
    assert status["backups"][0]["id"] == bid
    assert status["backups"][0]["role"] == "owner"
    assert status["backups"][0]["open"] is False   # locked again after create
    inside = server.root / "data/store" / f"{bid}.box" / "inside"
    assert json.loads((inside / "backup.json").read_text())["id"] == bid
    assert json.loads((inside / "owner.json").read_text())["owner"] == f"{1:032x}"
    assert (inside / "current" / "001").is_dir()


def test_create_refuses_bad_input(server):
    server.init()
    kid = server.add_computer(1)
    assert server.call(kid, "create 1000", b"{}")[0] == 1                     # too small
    assert "password and the key" in server.call(kid, f"create {2 << 30}", b"{}")[2]
    code, _, error = server.call(kid, f"create {200 << 30}",
                                 json.dumps({"password": "p", "key": "S0VZ"}).encode())
    assert code == 1 and "GiB free" in error


def test_unlock_with_key_or_password_then_lock(owned):
    server, kid, bid = owned
    hold = server.ok(kid, f"unlock {bid}", KEY)["hold"]
    assert server.ok(kid, "status")["backups"][0]["open"] is True
    assert server.ok(kid, f"points {bid}")["points"] == []
    assert server.ok(kid, f"lock {bid}") == {"locked": True, "holds": 0}
    assert server.ok(kid, f"unlock {bid}", b"correct horse")["hold"] != hold
    server.ok(kid, f"lock {bid}")


def test_wrong_password_is_refused_plainly(owned):
    server, kid, bid = owned
    code, _, error = server.call(kid, f"unlock {bid}", b"wrong")
    assert code == 1 and "doesn't open this backup" in error
    assert server.ok(kid, "status")["backups"][0]["open"] is False


def test_locked_backups_cant_be_looked_into(owned):
    server, kid, bid = owned
    code, _, error = server.call(kid, f"points {bid}")
    assert code == 1 and "locked" in error


def test_letting_go_of_a_hold_leaves_it_for_the_sweep(owned):
    server, kid, bid = owned
    a = server.ok(kid, f"unlock {bid}", KEY)["hold"]
    b = server.ok(kid, f"unlock {bid}", KEY)["hold"]
    assert server.ok(kid, f"lock {bid} {a}") == {"locked": False, "holds": 1}
    assert server.ok(kid, f"hold {bid} {b}") == {"hold": b}
    assert server.ok(kid, f"lock {bid} {b}") == {"locked": False, "holds": 0}
    assert server.call(kid, f"hold {bid} {b}")[0] == 1  # gone
    assert server.ok(kid, "status")["backups"][0]["open"] is True


def test_sweep_locks_only_when_nobody_holds_and_its_quiet(owned, monkeypatch):
    server, kid, bid = owned
    hold = server.ok(kid, f"unlock {bid}", KEY)["hold"]
    assert server.gate("sweep").returncode == 0
    assert server.ok(kid, "status")["backups"][0]["open"] is True   # held
    server.ok(kid, f"lock {bid} {hold}")
    server.gate("sweep")                                             # starts the quiet clock
    assert server.ok(kid, "status")["backups"][0]["open"] is True
    quiet = server.root / "run/omabackups-gate/turns" / f"{bid}.quiet"
    since, _, was = quiet.read_text().partition("\n")
    quiet.write_text(f"{float(since) - 601}\n{was}")                 # ...10 minutes pass
    server.gate("sweep")
    assert server.ok(kid, "status")["backups"][0]["open"] is False


def test_a_dead_jobs_hold_doesnt_keep_it_open(owned):
    server, kid, bid = owned
    hold = server.ok(kid, f"unlock {bid}", KEY)["hold"]
    mark = server.root / "run/omabackups-gate/holds" / bid / hold
    os.utime(mark, (0, 0))                       # nothing refreshed it for ages
    server.gate("sweep")                          # drops it, starts the quiet clock
    assert not mark.exists()
    quiet = server.root / "run/omabackups-gate/turns" / f"{bid}.quiet"
    since, _, was = quiet.read_text().partition("\n")
    quiet.write_text(f"{float(since) - 601}\n{was}")
    server.gate("sweep")
    assert server.ok(kid, "status")["backups"][0]["open"] is False
    assert "unlock again" in server.call(kid, f"hold {bid} {hold}")[2]


def test_other_computers_cant_see_or_touch_my_backup(owned):
    server, kid, bid = owned
    other = server.add_computer(2)
    for command in (f"unlock {bid}", f"points {bid}", f"lock {bid}", f"space {bid}"):
        code, _, error = server.call(other, command, KEY)
        assert code == 1 and "no such backup" in error, command
    assert server.ok(other, "status")["backups"] == []


def test_a_rescue_key_can_unlock_and_look_but_never_delete(owned):
    server, kid, bid = owned
    rescue = server.ok(kid, f"add-key {bid} 'Rescue USB'", make_pubkey(9).encode())["key"]
    inside = server.root / "data/store" / f"{bid}.box" / "inside" / "points"
    for name in ("001-2026-11-01-1000", "001-2026-11-02-1000"):
        (inside / name).mkdir()
    server.ok(rescue, f"unlock {bid}", b"correct horse")
    assert len(server.ok(rescue, f"points {bid}")["points"]) == 2
    for command in (f"delete {bid} 001-2026-11-01-1000", f"add-key {bid} more",
                    f"remove-key {bid} {kid}", f"create {2 << 30}"):
        code, _, error = server.call(rescue, command, make_pubkey(8).encode())
        assert code == 1, command
        assert "can't" in error or "only a computer" in error, (command, error)
    assert (inside / "001-2026-11-01-1000").is_dir()


def test_owner_deletes_but_never_the_newest_or_a_kept_one(owned):
    server, kid, bid = owned
    inside = server.root / "data/store" / f"{bid}.box" / "inside"
    for name in ("001-2026-11-01-1000", "001-2026-11-02-1000", "001-2026-11-03-1000"):
        (inside / "points" / name).mkdir()
    (inside / "kept.json").write_text(json.dumps({"kept": ["001-2026-11-02-1000"],
                                                  "return_point": None}))
    server.ok(kid, f"unlock {bid}", KEY)
    assert "newest" in server.call(kid, f"delete {bid} 001-2026-11-03-1000")[2]
    assert "kept" in server.call(kid, f"delete {bid} 001-2026-11-02-1000")[2]
    assert server.ok(kid, f"delete {bid} 001-2026-11-01-1000") == {"deleted": "001-2026-11-01-1000"}
    assert "not a restore point" in server.call(kid, f"delete {bid} ../../etc")[2]


def test_removing_a_rescue_key(owned):
    server, kid, bid = owned
    rescue = server.ok(kid, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    server.ok(kid, f"remove-key {bid} {rescue}")
    assert "isn't known" in server.call(rescue, "status")[2]
    keys = (server.root / "var/lib/omabackups-gate/home/.ssh/authorized_keys").read_text()
    assert rescue not in keys


def test_no_store_yet_is_explained(server):
    kid_done = server.gate("admin", "add-computer", "a" * 32, "c", input=make_pubkey(1).encode())
    kid = json.loads(kid_done.stdout)["key"]
    code, _, error = server.call(kid, f"create {2 << 30}",
                                 json.dumps({"password": "p", "key": "S0VZ"}).encode())
    assert code == 1 and "no backup store" in error


def test_addresses(owned):
    server, kid, bid = owned
    answer = server.ok(kid, "addresses")
    assert "127.0.0.1" not in answer["addresses"] and isinstance(answer["tailscale"], dict)
    assert server.call("0" * 16, "addresses")[0] == 1      # unknown keys get nothing
