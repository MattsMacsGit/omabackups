"""Damaged files sent again by name (audit 4.2; 1.x resend_damaged), and
counted, so damage again within three months says the disk may be failing."""

import json
import os
import time

from test_run import world  # noqa: F401  (the fixture)

from omabackups.backup import damaged, run


def damage(srv, bid: str, names: list) -> None:
    health = next(srv.root.rglob("registry.json")).parent / "health" / f"{bid}.json"
    health.parent.mkdir(parents=True, exist_ok=True)
    health.write_text(json.dumps({"state": "damaged", "files": names}))


def test_a_damaged_file_goes_again_whole_once(world, monkeypatch):  # noqa: F811
    srv, kid, bid, src, box = world
    names = iter(f"001-2099-01-0{i}-0000" for i in range(1, 9))
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    (src.root / "home/u/gone.txt").write_text("soon gone")
    first = run.backup(source=src)["point"]
    stored = box / "current/001/home/u/notes.txt"
    stat = stored.stat()
    stored.write_text("XXXXX")                               # rot: same size, same date
    os.utime(stored, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    (src.root / "home/u/gone.txt").unlink()
    damage(srv, bid, [f"points/{first}/home/u/notes.txt", f"current/001/home/u/notes.txt",
                      f"points/{first}/home/u/gone.txt"])
    second = run.backup(source=src)
    assert stored.read_text() == "hello"                     # a good copy again
    record = damaged.load()
    assert record["sent"] == ["home/u/notes.txt"] and record["missing"] == ["home/u/gone.txt"]
    assert second["how"]["home"].startswith("changes (")     # nothing else read again
    stored.write_text("YYYYY")
    os.utime(stored, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    run.backup(source=src)
    assert stored.read_text() == "YYYYY"                     # once: the same names aren't sent again


def test_damage_twice_in_three_months_says_the_disk_may_be_failing():
    now = time.time()
    assert not damaged.failing({"found": [now - 10]}, now)
    assert damaged.failing({"found": [now - 80 * 86400, now - 10]}, now)
    assert not damaged.failing({"found": [now - 100 * 86400, now - 10]}, now)


def test_names_inside_a_part():
    names = ["points/001-2026-11-01-1000/home/u/a.txt", "current/001/home/u/a.txt",
             "points/001-2026-11-01-1000/system/etc/x", "other/thing", "points/p/home/../../x"]
    assert damaged.damaged_in(names, "home") == {"u/a.txt": names[:2]}
