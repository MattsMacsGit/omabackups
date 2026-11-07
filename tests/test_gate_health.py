"""The health check on the fake server (a pretend scrub; the verdict rules are 1.x's)."""

import json
import os
import sys
from pathlib import Path

import pytest
from gate_harness import FakeServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "gate"))
KEY = b"K" * 64


@pytest.fixture
def box(tmp_path):
    srv = FakeServer(tmp_path / "server")
    srv.init()
    kid = srv.add_computer(1)
    bid = srv.create(kid)
    yield srv, kid, bid
    srv.close()


def fake_scrub(srv, bid, **state):
    path = srv.root / "run/omabackups-gate" / f"fake-scrub-{bid}.json"
    current = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps({**current, **state}))


def test_never_checked_is_unknown(box):
    srv, kid, bid = box
    assert srv.ok(kid, f"health {bid}")["state"] == "unknown"


def test_a_clean_pass_is_healthy(box):
    srv, kid, bid = box
    srv.ok(kid, f"unlock {bid}", KEY)
    assert srv.ok(kid, f"health-start {bid} 60")["running"] is True
    fake_scrub(srv, bid, status="finished", data_bytes_scrubbed=1000)
    answer = srv.ok(kid, f"health {bid}")
    assert answer["state"] == "healthy" and answer["running"] is False and answer["full_pass_at"]


def test_checksum_errors_mean_damaged_and_it_stands(box):
    srv, kid, bid = box
    srv.ok(kid, f"unlock {bid}", KEY)
    srv.ok(kid, f"health-start {bid} 60")
    fake_scrub(srv, bid, status="finished", csum_errors=3)
    assert srv.ok(kid, f"health {bid}")["state"] == "damaged"
    srv.ok(kid, f"health-start {bid} 60")              # a new pass begins...
    assert srv.ok(kid, f"health {bid}")["state"] == "damaged"   # ...and the warning stands


def test_the_sweep_keeps_it_open_while_checking_then_pauses_it(box):
    srv, kid, bid = box
    hold = srv.ok(kid, f"unlock {bid}", KEY)["hold"]
    srv.ok(kid, f"health-start {bid} 60")
    srv.ok(kid, f"lock {bid} {hold}")
    quiet = srv.root / "run/omabackups-gate/turns" / f"{bid}.quiet"
    srv.gate("sweep")
    assert srv.ok(kid, "status")["backups"][0]["open"] is True      # checking: stays open
    state = srv.root / "var/lib/omabackups-gate/health" / f"{bid}.json"
    record = json.loads(state.read_text())
    record["deadline"] = 1                                          # tonight's time is up
    state.write_text(json.dumps(record))
    srv.gate("sweep")                                               # pauses it, starts the clock
    since, _, was = quiet.read_text().partition("\n")
    quiet.write_text(f"{float(since) - 601}\n{was}")
    srv.gate("sweep")
    assert srv.ok(kid, "status")["backups"][0]["open"] is False
    assert json.loads((srv.root / "run/omabackups-gate" / f"fake-scrub-{bid}.json").read_text())["status"] != "running"


def test_rescue_keys_may_look_but_not_start(box):
    from gate_harness import make_pubkey
    srv, kid, bid = box
    rescue = srv.ok(kid, f"add-key {bid} stick", make_pubkey(9).encode())["key"]
    srv.ok(kid, f"unlock {bid}", KEY)
    assert srv.call(rescue, f"health-start {bid} 60")[0] == 1
    assert srv.ok(rescue, f"health {bid}")["state"] == "unknown"


def test_verdict_rules():
    os.environ.setdefault("OMABACKUPS_GATE_ROOT", "/nonexistent")
    import health
    assert health.verdict({}) == "unknown"
    assert health.verdict({"checked_at": 1}) == "healthy"
    assert health.verdict({"checked_at": 1, "device": {"read_io_errs": 2},
                           "device_base": {"read_io_errs": 0}}) == "warning"
    assert health.verdict({"checked_at": 1, "device": {"read_io_errs": 2},
                           "device_base": {"read_io_errs": 2}}) == "healthy"   # old errors only
    assert health.verdict({"checked_at": 1, "files": ["x"]}) == "damaged"


def test_the_check_stands_aside_for_a_backup_and_carries_on(box):
    srv, kid, bid = box
    night = srv.ok(kid, f"unlock {bid}", KEY)["hold"]
    srv.ok(kid, f"health-start {bid} 60")
    scrub = srv.root / "run/omabackups-gate" / f"fake-scrub-{bid}.json"
    backup = srv.ok(kid, f"unlock {bid}", KEY)["hold"]          # a backup arrives
    assert json.loads(scrub.read_text())["status"] != "running"
    assert srv.ok(kid, f"health {bid}")["running"] is True      # paused, still under way
    srv.ok(kid, f"lock {bid} {backup}")                          # the backup is done
    assert json.loads(scrub.read_text())["status"] == "running"
    srv.ok(kid, f"lock {bid} {night}")


def test_a_backup_that_died_doesnt_leave_the_check_paused(box):
    srv, kid, bid = box
    srv.ok(kid, f"unlock {bid}", KEY)
    srv.ok(kid, f"health-start {bid} 60")
    backup = srv.ok(kid, f"unlock {bid}", KEY)["hold"]
    mark = srv.root / "run/omabackups-gate/holds" / bid / backup
    os.utime(mark, (0, 0))                                        # it died: nothing refreshes it
    srv.gate("sweep")
    scrub = srv.root / "run/omabackups-gate" / f"fake-scrub-{bid}.json"
    assert json.loads(scrub.read_text())["status"] == "running"
