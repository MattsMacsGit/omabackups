"""D67: the panel says when the backup server's gatekeeper is older than the
one this omabackups carries, with Update it (`setup server --update`)."""

import re
from pathlib import Path

from test_run import world  # noqa: F401  (the fixture)

from omabackups.backup import run
from omabackups.commands import status_data
from omabackups.core import config, flow, state
from omabackups.where.server import GATE_LATEST, SERVER_GATE

ROOT = Path(__file__).resolve().parent.parent


def kinds(record: dict) -> set:
    return {line["kind"] for line in status_data.lines(flow.Step.EVERYDAY, config.defaults(), record,
                                                       {}, {"rescue_usb": True})}


def test_the_version_it_expects_is_the_one_it_carries():
    conf = (ROOT / "server/gate/conf.py").read_text()
    assert int(re.search(r"^VERSION = (\d+)", conf, re.M).group(1)) == GATE_LATEST


def test_an_older_server_is_said_with_update_it(sandbox):
    line = next(x for x in status_data.lines(flow.Step.EVERYDAY, config.defaults(), {"gate": GATE_LATEST - 1},
                                             {}, {"rescue_usb": True}) if x["kind"] == "server-update")
    assert line["colour"] == "yellow" and line["action"] == "server-update"
    assert line["title"] == "Your backup server needs an update" and "sudo" in line["text"]


def test_an_up_to_date_server_a_disk_or_no_backup_yet_says_nothing(sandbox):
    assert "server-update" not in kinds({"gate": GATE_LATEST})
    assert "server-update" not in kinds({"gate": None})                 # a backup disk: always current
    assert "server-update" not in kinds({})                             # no backup since this version


def test_the_line_goes_as_soon_as_the_update_finished(sandbox):
    assert "server-update" in kinds({"gate": GATE_LATEST - 1})
    state.write(SERVER_GATE, {"gate": GATE_LATEST})                     # setup server --update wrote it
    assert "server-update" not in kinds({"gate": GATE_LATEST - 1})


def test_each_backup_keeps_the_servers_version(world):  # noqa: F811
    srv, kid, bid, src, box = world
    run.backup(source=src)
    assert run.load_record()["gate"] == GATE_LATEST                    # this package's, on the server
