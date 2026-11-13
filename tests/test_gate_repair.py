"""Repairing a backup on the gatekeeper (audit 1.7, 1.8): a line's working
copy rebuilt from a restore point, and any restore point deleted when the
command line asks for it."""

import json

from gate_harness import make_pubkey
from test_gate_migrate import join, two  # noqa: F401  (two: the fixture)

POINT = "001-2026-11-07-2102"


def test_rebuild_puts_the_point_back_as_the_working_copy(two):  # noqa: F811
    srv, old, new, bid, hold, inside = two
    notes = inside / "current/001/home/u/notes.txt"
    notes.write_text("damaged")
    (inside / "current/001/home/u/stray.txt").write_text("not in the point")
    assert srv.ok(old, f"rebuild {bid} 001 {POINT}") == {"rebuilt": "001", "from": POINT}
    assert notes.read_text() == "from the old computer"
    assert not (inside / "current/001/home/u/stray.txt").exists()
    assert sorted(p.name for p in (inside / "current").iterdir()) == ["001"]     # nothing left beside it
    assert (inside / "points" / POINT / "home/u/notes.txt").read_text() == "from the old computer"


def test_rebuild_tidies_what_a_cut_off_one_left(two):  # noqa: F811
    srv, old, new, bid, hold, inside = two
    (inside / "current/001.new/home").mkdir(parents=True)
    srv.ok(old, f"rebuild {bid} 001 {POINT}")
    assert sorted(p.name for p in (inside / "current").iterdir()) == ["001"]


def test_only_the_owner_rebuilds_its_own_line(two):  # noqa: F811
    srv, old, new, bid, hold, inside = two
    join(srv, new)                                                  # a reader now
    rescue = srv.ok(old, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    for kid in (new, rescue):
        assert srv.call(kid, f"rebuild {bid} 001 {POINT}")[0] == 1
    for command, why in ((f"rebuild {bid} 002 {POINT}", "no backup line"),
                         (f"rebuild {bid} 001 001-2026-01-01-0000", "no such restore point"),
                         (f"rebuild {bid} 001 ../../etc", "not a restore point")):
        code, _, error = srv.call(old, command)
        assert code == 1 and why in error, (command, error)


def test_a_handed_over_line_cant_be_rebuilt(two):  # noqa: F811
    srv, old, new, bid, hold, inside = two
    join(srv, new)
    srv.ok(new, f"handover {bid} {POINT}")
    assert "read only" in srv.call(new, f"rebuild {bid} 001 {POINT}")[2]
    assert srv.ok(new, f"rebuild {bid} 002 {POINT}")["rebuilt"] == "002"


def test_delete_any_takes_the_newest_and_a_kept_one(two):  # noqa: F811
    srv, old, new, bid, hold, inside = two
    srv.ok(old, f"snapshot {bid} 001 001-2026-11-08-0900", b"{}")
    srv.ok(old, f"keep {bid} {POINT}")
    assert "kept" in srv.call(old, f"delete {bid} {POINT}")[2]                     # the panel's way
    assert "newest" in srv.call(old, f"delete {bid} 001-2026-11-08-0900")[2]
    assert "can only be" in srv.call(old, f"delete {bid} {POINT} please")[2]
    srv.ok(old, f"delete {bid} {POINT} any")
    srv.ok(old, f"delete {bid} 001-2026-11-08-0900 any")
    info = srv.ok(old, f"points {bid}")
    assert info["points"] == [] and info["kept"]["kept"] == []


def test_delete_any_lets_go_of_the_return_point(two):  # noqa: F811
    srv, old, new, bid, hold, inside = two
    join(srv, new)
    srv.ok(new, f"handover {bid} {POINT}")
    srv.ok(new, f"delete {bid} {POINT} any")
    assert json.loads((inside / "kept.json").read_text())["return_point"] is None
