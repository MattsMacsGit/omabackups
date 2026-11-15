"""The panel hears a backup start at once (15 Nov 2026): away from home,
finding the server took over a minute, and the panel went back to the last
run's "waiting" words meanwhile, then a backup suddenly ran."""

import pytest

from omabackups.backup import progress, run
from omabackups.core.errors import OmaError


def test_starting_is_written_before_the_server_is_found(sandbox, monkeypatch):
    progress.write({"running": False, "ok": False, "waiting": "away", "kind": "now"})   # the last run
    seen = {}

    def connect(server):
        seen["then"] = progress.read()
        raise OmaError("Your backup can't be reached.", code="unreachable")
    monkeypatch.setattr(run.location, "load", lambda: {})
    monkeypatch.setattr(run.location, "connect", connect)
    with pytest.raises(OmaError):
        run.backup(progress.reporter("anyway"), anyway=True)
    assert seen["then"]["running"] and seen["then"]["step"] == "starting"
    assert seen["then"]["kind"] == "anyway"
    assert progress.text(seen["then"]) == "Starting the backup..."
