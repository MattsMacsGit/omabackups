"""The Rescue USB (5.7, D11, D47): its settings and read-only key; one stick
at a time; on the stick, the settings where a computer keeps its own; the
wizard's Wi-Fi list read from iwd."""

import json
import os

import pytest
from gate_harness import GATE
from test_run import world  # noqa: F401  (world: the fixture)

from omabackups.backup import run
from omabackups.core import paths, rootjob
from omabackups.core.errors import OmaError
from omabackups.rescue import settings, wifi
from omabackups.where.server import Gate


def roles(srv, bid) -> dict:
    data = json.loads((srv.root / "var/lib/omabackups-gate/registry.json").read_text())
    return data["backups"][bid]["roles"]


def test_a_stick_gets_a_read_only_key_and_the_last_one_is_cut_off(world, monkeypatch, tmp_path):
    srv, kid, bid, src, box = world
    run.backup(source=src)
    first = rootjob.run("rescue-key", {})["settings"]
    k1 = json.loads(first["rescue.json"])["key"]
    assert roles(srv, bid)[k1] == "rescue"
    assert first["ssh_key"].startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    server = json.loads(first["server.json"])
    assert server["backup"] == bid and "address" in server
    second = rootjob.run("rescue-key", {})["settings"]
    k2 = json.loads(second["rescue.json"])["key"]
    assert k2 != k1 and roles(srv, bid)[k2] == "rescue" and k1 not in roles(srv, bid)    # D11

    # On the stick: the password opens it, read only.
    monkeypatch.setenv("OMABACKUPS_TEST_GATE", f"{GATE}:{k2}")
    stick = Gate("test")
    with pytest.raises(OmaError):
        stick.call("unlock", bid, data=b"wrong")
    hold = stick.call("unlock", bid, data=b"password1")["hold"]
    points = stick.call("points", bid)["points"]
    assert points
    with pytest.raises(OmaError):
        stick.call("delete", bid, points[0])                     # never changes the backup
    stick.call("lock", bid, hold)


def test_on_the_stick_the_settings_go_where_a_computer_keeps_its_own(sandbox, tmp_path):
    bundle = {"rescue.json": json.dumps({"key": "k", "computer": "laptop"}),
              "server.json": json.dumps({"address": "192.0.2.34", "backup": "b" * 32, "line": "004"}),
              "ssh_key": "PRIVATE\n", "known_hosts": "omabackups-server ssh-ed25519 AAAA\n"}
    folder = tmp_path / "stick"
    settings.write(bundle, folder)
    assert oct(os.stat(folder / "ssh_key").st_mode & 0o777) == "0o600"
    mine = settings.install(folder)
    assert mine["computer"] == "laptop"
    saved = json.loads(paths.server_file().read_text())
    assert saved["kind"] == "server" and saved["line"] == "004"
    assert (paths.keys_dir() / "ssh_key").read_text() == "PRIVATE\n"
    assert oct(os.stat(paths.keys_dir() / "ssh_key").st_mode & 0o777) == "0o600"
    assert paths.known_hosts_file().read_text().startswith("omabackups-server")


def test_the_wifi_list_is_read_from_iwd():
    table = """
                               Available networks
--------------------------------------------------------------------------------
      Network name                      Security            Signal
--------------------------------------------------------------------------------
  \x1b[1;90m> \x1b[0m Home Wi-Fi                        psk                 ****
      Cafe Free                         open                ***
      Work Net 5G                       8021x               **
"""
    assert wifi.parse_networks(table) == [
        {"name": "Home Wi-Fi", "security": "psk", "signal": "****"},
        {"name": "Cafe Free", "security": "open", "signal": "***"},
        {"name": "Work Net 5G", "security": "8021x", "signal": "**"}]
