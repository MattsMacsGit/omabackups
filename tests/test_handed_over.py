"""D22a: the old computer after a Migrate. Its line is read-only; a backup
stops before sending anything and says so plainly (it said "a reader key
can't do that", demo film, 15 Nov); Set up a new backup gives it a line of
its own, from its last restore point, and backups carry on there."""

import json
from datetime import datetime

import pytest
from test_run import world  # noqa: F401  (the fixture)

from omabackups.backup import handed, progress, run
from omabackups.commands import status_data
from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.root import job_newline


def _hand_over(box, to: str = "f" * 32, since: int = 1_794_700_000) -> None:
    """What a handover leaves (gatekeeper: verbs_migrate._new_line)."""
    lines = json.loads((box / "lines.json").read_text())["lines"] if (box / "lines.json").exists() else \
        [{"line": "001", "owner": "", "read_only": False}]
    for entry in lines:
        entry["read_only"] = True
    lines.append({"line": "002", "owner": to, "read_only": False})
    (box / "lines.json").write_text(json.dumps({"lines": lines}))
    (box / "owner.json").write_text(json.dumps({"owner": to, "since": since, "history": []}))


def test_the_old_computer_stops_and_says_why_then_carries_on_in_a_line_of_its_own(world):  # noqa: F811
    srv, kid, bid, src, box = world
    first = run.backup(source=src)["point"]
    _hand_over(box)
    with pytest.raises(OmaError) as caught:
        run.backup(source=src)
    assert caught.value.code == "handed-over"
    assert "took this backup over (Migrate) on" in caught.value.what
    assert "can still bring files back, but no longer backs up into it" in caught.value.what
    assert sorted(p.name for p in (box / "points").iterdir()) == [first]       # nothing made

    answer = job_newline.new_line({})                                         # Set up a new backup
    assert answer["from"] == first and answer["line"] != "001"
    assert json.loads(paths.server_file().read_text())["line"] == answer["line"]
    again = run.backup(source=src)["point"]
    assert again.startswith(answer["line"] + "-")


def test_it_names_the_new_computer_and_the_day():
    since = 1_794_700_000

    class Gate:
        def call(self, verb, *args):
            if verb == "points":
                return {"points": ["001-2026-11-14-1418", "002-2026-11-15-1240"],
                        "lines": [{"line": "001", "owner": "a", "read_only": True},
                                  {"line": "002", "owner": "b", "read_only": False}],
                        "owner": {"owner": "b", "since": since}}
            return {"point": {"computer": "new-laptop"}} if args[1] == "002-2026-11-15-1240" else {}
    with pytest.raises(OmaError) as caught:
        handed.check(Gate(), "bid", "001")
    day = datetime.fromtimestamp(since).strftime("%a %-d %b")
    assert caught.value.what == (f"new-laptop took this backup over (Migrate) on {day}. This computer can "
                                 "still bring files back, but no longer backs up into it.")
    handed.check(Gate(), "bid", "002")                                        # the new computer: fine


def test_the_panel_shows_the_line_with_its_button(sandbox):
    progress.write({"running": False, "ok": False, "kind": "now", "error": OmaError(
        "new-laptop took this backup over (Migrate) on Sun 15 Nov. ...", "x", code="handed-over").as_dict()})
    got = [entry for entry in status_data.lines(None, {"automatic.on": True}, {}, progress.read(), {})
           if entry["kind"] == "handed-over"]
    assert got[0]["title"] == "This computer's backup was handed over"
    assert got[0]["action"] == "new-line" and got[0]["offer"].startswith("A backup line of its own")


def test_it_starts_from_this_computers_last_point_on_its_old_line():
    points = ["001-2026-11-14-1418", "001-2026-11-15-1209", "002-2026-11-15-1240"]
    assert job_newline.start_from(points, "001", "001-2026-11-14-1418") == "001-2026-11-14-1418"   # rescued from
    assert job_newline.start_from(points, "001", None) == "001-2026-11-15-1209"                   # its newest
    assert job_newline.start_from(points, "003", None) is None
