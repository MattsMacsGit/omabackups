"""D63: Restore my files shows the backup's own progress (percent of a known
total, amount, speed, time left), not rsync's rounded percentage of
everything (it sat at 0% for minutes while files came back, 25 Nov)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from omabackups.restore import progress

# rsync 3.5.1's --info=progress2, as it really comes (\r between updates).
RSYNC = (b"\r         32,768B   0%    0B/s    0:00:00  \r     21,954,560B  43%   20,526,022B/s    0:00:01  "
         b"\r     30,000,000B  60%   21,512,729B/s    0:00:01 (xfr#1, to-chk=1/3)\r     43,828,096B  87%")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_the_total_comes_from_the_measured_restore_point():
    sizes = {"home": {"": [900, 9], "u": [800, 8], "u/Documents": [300, 3], "u/Music": [200, 2]}}
    assert progress.planned(sizes, "u", None, None) == 800
    assert progress.planned(sizes, "u", ["Documents", "Music/"], None) == 500
    assert progress.planned(sizes, "u", None, ["/Music"]) == 0          # the chooser sends its own
    assert progress.planned(sizes, "u", None, ["/Music"], given=600) == 600
    assert progress.planned(None, "u", None, None) == 0                 # an older server


def test_listing_first_then_bringing_back_with_the_backups_numbers():
    said, clock = [], Clock()
    state = {"running": True}
    watch = progress.Watch(state, 100_000_000, lambda s: said.append(dict(s)), clock=clock)
    assert state["step"] == "list" and not said                # rsync is still listing the files
    watch.feed(RSYNC[:60])
    assert said[-1]["step"] == "bring" and said[-1]["sent"] == 32_768
    clock.now += 2
    watch.feed(RSYNC[60:])
    last = said[-1]
    # the last update is cut off mid-line: the last whole one counts
    assert last["sent"] == 30_000_000 and last["total"] == 100_000_000
    assert last["percent"] == 30 and last["speed"] > 0          # of the restore's total, not rsync's 60%
    assert set(last) >= {"step", "percent", "sent", "total", "speed", "left"}


def test_it_writes_at_most_once_a_second():
    said, clock = [], Clock()
    watch = progress.Watch({}, 100_000_000, lambda s: said.append(dict(s)), clock=clock)
    for n in range(1, 50):
        watch.feed(f"\r {n * 1000:,}B  1%  1,000B/s  0:00:01 ".encode())
    assert len(said) == 1                                       # the first, then a second later
    clock.now += 1.1
    watch.feed(b"\r 99,000B  1%  1,000B/s  0:00:01 ")
    assert len(said) == 2 and said[-1]["sent"] == 99_000


def _detail(running):
    if not shutil.which("node"):
        pytest.skip("node isn't installed")
    code = (Path(__file__).resolve().parent.parent / "plugin/Model.js").read_text().replace(".pragma library", "")
    done = subprocess.run(["node", "-e", code + f"\nprocess.stdout.write(detail({json.dumps(running)}))"],
                          capture_output=True, text=True, check=True)
    return done.stdout


def test_the_panel_says_it_as_a_backup_does():
    text = _detail({"step": "bring", "percent": 12, "sent": 38_000_000_000, "total": 310_000_000_000,
                    "speed": 85_000_000, "left": 3600})
    assert text.startswith("12% · 38") and "of 310" in text and "/s" in text and "about 1 h left" in text
    assert _detail({"step": "bring", "sent": 2_000_000_000, "total": 0, "speed": 0}).endswith("so far")
    assert _detail({"step": "list"}) == ""                      # still listing: the sweeping line
