"""Migrate on the gatekeeper (D22, D22a): join with the backup's password, read
while migrating, then the handover into a new line; and a line of its own."""

import base64
import json

import pytest
from gate_harness import FakeServer

PASSWORD = "correct horse"


@pytest.fixture
def two(tmp_path):
    """The old computer (1) with a backup and one restore point; a new one (2)."""
    srv = FakeServer(tmp_path / "server")
    srv.init()
    old = srv.add_computer(1)
    bid = srv.create(old, password=PASSWORD)
    hold = srv.ok(old, f"unlock {bid}", PASSWORD.encode())["hold"]
    inside = srv.root / "data/store" / f"{bid}.box" / "inside"
    (inside / "current/001/home/u").mkdir(parents=True)
    (inside / "current/001/home/u/notes.txt").write_text("from the old computer")
    srv.ok(old, f"snapshot {bid} 001 001-2026-11-07-2102", b"{}")
    new = srv.add_computer(2)
    yield srv, old, new, bid, hold, inside
    srv.close()


def join(srv, kid, password=PASSWORD, key=b"N" * 64):
    return srv.call(kid, "join", json.dumps({"password": password,
                                             "key": base64.b64encode(key).decode()}).encode())


def test_a_wrong_password_finds_nothing_and_gives_nothing(two):
    srv, old, new, bid, hold, inside = two
    code, _, error = join(srv, new, "wrong")
    assert code == 1 and "doesn't open any backup" in error
    code, _, error = srv.call(new, f"points {bid}")
    assert code == 1 and "no such backup" in error        # still can't even see it


def test_join_lets_a_new_computer_read_but_not_write(two):
    srv, old, new, bid, hold, inside = two
    code, out, _ = join(srv, new)
    assert code == 0 and out["backups"][0]["id"] == bid
    assert srv.ok(new, f"unlock {bid}", b"N" * 64)["hold"]          # its own key file now
    assert "001-2026-11-07-2102" in srv.ok(new, f"points {bid}")["points"]
    for command in (f"snapshot {bid} 001 001-2026-11-08-0900", f"delete {bid} 001-2026-11-07-2102"):
        code, _, error = srv.call(new, command, b"{}")
        assert code == 1, command


def test_handover_a_new_line_from_the_point_and_the_old_one_read_only(two):
    srv, old, new, bid, hold, inside = two
    join(srv, new)
    answer = srv.ok(new, f"handover {bid} 001-2026-11-07-2102")
    assert answer == {"line": "002", "from": "001-2026-11-07-2102", "return_point": "001-2026-11-07-2102"}
    assert (inside / "current/002/home/u/notes.txt").read_text() == "from the old computer"
    lines = {e["line"]: e for e in json.loads((inside / "lines.json").read_text())["lines"]}
    assert lines["001"]["read_only"] and not lines["002"]["read_only"]
    assert lines["002"]["owner"] == f"{2:032x}"
    assert json.loads((inside / "kept.json").read_text())["return_point"] == "001-2026-11-07-2102"
    owner = json.loads((inside / "owner.json").read_text())
    assert owner["owner"] == f"{2:032x}" and owner["history"][0]["from"] == f"{1:032x}"
    # The new computer backs up into its line; the old one can't any more, but can read.
    srv.ok(new, f"snapshot {bid} 002 002-2026-11-08-0900", b"{}")
    code, _, error = srv.call(old, f"snapshot {bid} 001 001-2026-11-08-1000", b"{}")
    assert code == 1
    assert "002-2026-11-08-0900" in srv.ok(old, f"points {bid}")["points"]
    code, _, _ = srv.call(old, f"delete {bid} 001-2026-11-07-2102")
    assert code == 1                                   # no deletes once handed over


def test_the_old_computer_can_start_a_line_of_its_own(two):
    srv, old, new, bid, hold, inside = two
    join(srv, new)
    srv.ok(new, f"handover {bid} 001-2026-11-07-2102")
    answer = srv.ok(old, f"newline {bid} 001-2026-11-07-2102")      # Set up a new backup
    assert answer["line"] == "003" and answer["return_point"] is None
    srv.ok(old, f"snapshot {bid} 003 003-2026-11-08-1100", b"{}")
    srv.ok(new, f"snapshot {bid} 002 002-2026-11-08-1100", b"{}")    # the new one carries on too
