"""The point a rescue restores from (audit 1.4, 9.3): kept the moment it's
picked on the stick; nothing but a command-line delete removes it while the
restore is unfinished; once everything came back and a normal backup ran,
the keep lets go; after a forced backup it stays."""

import json

from gate_harness import make_pubkey
from test_gate import KEY, owned, server  # noqa: F401  (fixtures)
from test_run import world  # noqa: F401  (the fixture)

from omabackups.backup import run
from omabackups.core import flow, state

OLD, NEW = "001-2026-11-01-1000", "001-2026-11-02-1000"


def stick(srv, kid, bid):
    rescue = srv.ok(kid, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    return rescue


def test_the_stick_keeps_and_only_delete_any_takes_it(owned):  # noqa: F811
    server, kid, bid = owned
    rescue = stick(server, kid, bid)
    inside = server.root / "data/store" / f"{bid}.box" / "inside"
    for name in (OLD, NEW):
        (inside / "points" / name).mkdir()
    server.ok(rescue, f"unlock {bid}", KEY)
    server.ok(rescue, f"keep {bid} {OLD}")
    assert server.ok(kid, f"points {bid}")["kept"]["by"] == {OLD: "rescue"}
    assert server.call(rescue, f"release {bid} {OLD}")[0] == 1                  # the stick never lets go
    assert "only omabackups delete" in server.call(kid, f"release {bid} {OLD}")[2]   # nor the panel
    assert server.call(kid, f"delete {bid} {OLD}")[0] == 1                      # nor thinning
    server.ok(kid, f"delete {bid} {OLD} any")                                   # the command line can
    kept = server.ok(kid, f"points {bid}")["kept"]
    assert kept["kept"] == [] and kept["by"] == {}


def test_rescue_done_lets_go_of_a_rescues_keep_only(owned):  # noqa: F811
    server, kid, bid = owned
    rescue = stick(server, kid, bid)
    inside = server.root / "data/store" / f"{bid}.box" / "inside"
    for name in (OLD, NEW):
        (inside / "points" / name).mkdir()
    server.ok(kid, f"unlock {bid}", KEY)
    server.ok(kid, f"keep {bid} {NEW}")                                         # yours, from the panel
    server.ok(rescue, f"keep {bid} {OLD}")
    server.ok(kid, f"release {bid} {NEW} rescue-done")
    server.ok(kid, f"release {bid} {OLD} rescue-done")
    assert server.ok(kid, f"points {bid}")["kept"]["kept"] == [NEW]            # your keep stays
    assert server.call(rescue, f"release {bid} {NEW} rescue-done")[0] == 1


def rescued(point: str, files: list) -> None:
    state.write(flow.MIGRATE, {"done": True, "files_restored": not files, "rescued": True,
                               "point": point, "from_user": "u", "files": files, "at": 1})


def kept_by_rescue(srv, kid, bid, point: str) -> None:
    rescue = stick(srv, kid, bid)
    srv.ok(rescue, f"unlock {bid}", b"password1")
    srv.ok(rescue, f"keep {bid} {point}")


def test_after_a_full_rescue_the_next_backup_lets_the_keep_go(world, monkeypatch):  # noqa: F811
    srv, kid, bid, src, box = world
    names = iter(["001-2099-01-01-0000", "001-2099-01-02-0000", "001-2099-01-03-0000"])
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    first = run.backup(source=src)["point"]
    kept_by_rescue(srv, kid, bid, first)
    rescued(first, [])                                       # a Full Rescue: everything came back
    run.backup(source=src)
    kept = json.loads((box / "kept.json").read_text())
    assert first not in kept["kept"] and run.load_record()["rescue_settled"] == first
    run.backup(source=src)                                   # once only
    assert run.load_record()["rescue_settled"] == first


def test_after_a_forced_backup_the_keep_stays(world, monkeypatch):  # noqa: F811
    srv, kid, bid, src, box = world
    names = iter(["001-2099-01-01-0000", "001-2099-01-02-0000", "001-2099-01-03-0000"])
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    first = run.backup(source=src)["point"]
    kept_by_rescue(srv, kid, bid, first)
    rescued(first, ["Documents"])
    run.backup(source=src, force_after_restore=True)
    run.backup(source=src)                                   # a normal one after: still kept
    kept = json.loads((box / "kept.json").read_text())
    assert first in kept["kept"] and kept["by"] == {first: "rescue"}
    assert run.load_record()["kept_by"] == {first: "rescue"}


def test_the_tags_say_who_kept_it():
    from omabackups.commands import status_data
    record = {"all_points": [OLD, NEW, "001-2026-11-03-1000"], "kept": [OLD, NEW],
              "kept_by": {OLD: "rescue"}, "return_point": "001-2026-11-03-1000"}
    tags = {p["name"]: (p["kept"], p["kept_by"]) for p in status_data.points(record)}
    assert tags == {OLD: (True, "restore"), NEW: (True, ""), "001-2026-11-03-1000": (False, "migrate")}
