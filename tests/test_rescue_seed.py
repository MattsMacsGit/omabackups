"""After a rescue, the first backup is quick (stage 10):
snapshots only when the rescued point is its line's newest; the restored
record brought up to that point."""

import json

from omabackups.restore import seed


def test_only_the_newest_point_of_its_line_is_seeded():
    points = ["003-2026-11-09-1928", "004-2026-11-10-1753", "004-2026-11-10-2103", "005-2026-11-11-0900"]
    assert seed.newest_of_line("004-2026-11-10-2103", points)
    assert not seed.newest_of_line("004-2026-11-10-1753", points)       # going back: full check
    assert seed.newest_of_line("005-2026-11-11-0900", points)
    assert not seed.newest_of_line("006-2026-11-12-0000", points)


def test_the_restored_record_is_brought_up_to_the_rescued_point(tmp_path):
    rec = tmp_path / "backup.json"
    rec.write_text(json.dumps({"finished": False, "since": {"system": "system-old", "home": "home-old"},
                               "skips": {"system": "s1", "home": "h1"}, "last_point": "004-2026-11-10-1753",
                               "kept": ["x"]}))
    seed.point_record(rec, "004-2026-11-10-2103", {"system": "system-new"})          # Quick: system only
    got = json.loads(rec.read_text())
    assert got["since"] == {"system": "system-new"} and got["finished"] is True
    assert got["last_point"] == "004-2026-11-10-2103" and got["kept"] == ["x"]
    assert got["skips"] == {"system": "s1"}                     # home: checked file by file
    seed.point_record(rec, "004-2026-11-10-2103", {"system": "a", "home": "b"})       # Full
    assert json.loads(rec.read_text())["since"] == {"system": "a", "home": "b"}
