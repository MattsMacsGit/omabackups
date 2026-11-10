"""Finding the backup server (D48): by name or address, home first, then
name.local, then Tailscale (away); home addresses learnt from the server so a
new address from the router never sends backups over Tailscale."""

import json

import pytest

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.where import network


def test_tailscale_addresses_and_names_are_away():
    assert network.tailscale("100.101.102.103") and network.tailscale("fd7a:115c:a1e0::53")
    assert network.tailscale("server.tail1234.ts.net") and network.tailscale("server.tail1234.ts.net.")
    assert not network.tailscale("192.0.2.34") and not network.tailscale("192.168.1.20")
    assert not network.tailscale("server.local")


def test_the_order_home_then_local_then_away(sandbox):
    server = {"address": "server", "home": ["192.0.2.40"], "away": ["server.tail1.ts.net", "100.101.102.104"]}
    assert network.candidates(server) == [("192.0.2.40", False), ("server", False), ("server.local", False),
                                          ("server.tail1.ts.net", True), ("100.101.102.104", True)]
    typed_ts = {"address": "100.101.102.104", "home": ["192.0.2.40"], "away": []}
    assert network.candidates(typed_ts) == [("192.0.2.40", False), ("100.101.102.104", True)]


def test_a_new_address_from_the_router_still_counts_as_home(sandbox, monkeypatch):
    server = {"address": "192.0.2.34", "home": ["192.0.2.50"], "away": ["100.101.102.104"]}
    monkeypatch.setenv("OMABACKUPS_TEST_REACHABLE", "192.0.2.50,100.101.102.104")
    assert network.route(server) == ("192.0.2.50", False)
    monkeypatch.setenv("OMABACKUPS_TEST_REACHABLE", "100.101.102.104")
    assert network.route(server) == ("100.101.102.104", True)
    monkeypatch.setenv("OMABACKUPS_TEST_REACHABLE", "nothing")
    with pytest.raises(OmaError) as caught:
        network.route(server)
    assert "192.0.2.50" in caught.value.details and "100.101.102.104" in caught.value.details


def test_what_the_server_says_is_split_into_home_and_away():
    home, away = network.split({"addresses": ["127.0.0.1", "fe80::1", "fd00::5", "192.0.2.50", "100.101.102.104",
                                              "fd7a:115c:a1e0::1"],
                                "tailscale": {"name": "server.tail1.ts.net", "ips": ["100.101.102.104"]}})
    assert home == ["192.0.2.50", "fd00::5"]
    assert away == ["server.tail1.ts.net", "100.101.102.104"]


class FakeGate:
    def __init__(self, found):
        self.found = found

    def call(self, verb, *args, **kw):
        return {"gate": 15} if verb == "version" else self.found


def test_learnt_addresses_are_saved(sandbox):
    paths.server_file().parent.mkdir(parents=True, exist_ok=True)
    server = {"address": "server", "away": []}
    paths.server_file().write_text(json.dumps(server))
    network.learn_addresses(FakeGate({"addresses": ["192.0.2.50"], "tailscale": {"ips": ["100.101.102.104"]}}), server)
    saved = json.loads(paths.server_file().read_text())
    assert saved["home"] == ["192.0.2.50"] and saved["away"] == ["100.101.102.104"] and saved["address"] == "server"
