"""D50: a backup that won't fit says so plainly, before anything is sent, and
the reason is on screen with the picker to choose again."""

import subprocess

import pytest
from test_run import world  # noqa: F401 - a fixture

from omabackups.backup import run
from omabackups.backup.send import Sender
from omabackups.commands import status_data
from omabackups.core import config, flow
from omabackups.core.errors import OmaError
from omabackups.where.server import Gate


def test_a_full_backup_that_wont_fit_stops_before_sending(world, monkeypatch):
    srv, kid, bid, src, box = world
    real_call = Gate.call

    def call(self, verb, *args, **kwargs):
        if verb == "space":
            return {"box": 2 << 30, "used": 2 << 30, "free": 10}
        return real_call(self, verb, *args, **kwargs)
    monkeypatch.setattr(Gate, "call", call)

    def no_copy(*args, **kwargs):
        raise AssertionError("something was sent")
    monkeypatch.setattr(Sender, "copy", no_copy)
    with pytest.raises(OmaError) as caught:
        run.backup(source=src)
    assert caught.value.code == "backup-full"
    assert caught.value.what.startswith("This won't fit on your backup location: it needs")
    assert "Choose what gets backed up" in caught.value.todo and "new disk" in caught.value.todo


def test_running_out_of_room_mid_copy_is_said_plainly(monkeypatch):
    class Gateish:
        def rsh(self):
            return "ssh"

        def rsync_target(self):
            return "server"

        def rsync_env(self):
            return {}
    monkeypatch.setattr("omabackups.backup.send.subprocess.run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 11, b"", b'rsync: [receiver] write failed on "x": No space left on device (28)\n'))
    from omabackups.backup.skips import Skips
    with pytest.raises(OmaError) as caught:
        Sender(Gateish(), "b", "001").full("home", "/tmp", Skips([]))
    assert caught.value.code == "backup-full" and "won't fit" in caught.value.what


def test_the_reason_is_a_line_that_offers_the_picker(sandbox):
    now = {"running": False, "ok": False,
           "error": {"code": "backup-full", "what": "This won't fit on your backup location.",
                     "todo": "Remove some files.", "details": "box 1 TB"}}
    lines = status_data.lines(flow.Step.SETTING_UP, config.defaults(), {}, now, {})
    full = next(line for line in lines if line["kind"] == "full")
    assert full["colour"] == "red" and full["action"] == "pick"
    assert full["title"] == "This won't fit on your backup location"
