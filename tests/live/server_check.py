"""Stage 2's check on a real backup server, after `omabackups setup server`.

Run on the computer as root (it uses the root-only keys):
    sudo python3 tests/live/server_check.py

1. This computer's key: unlock, look inside, lock.
2. A throwaway rescue key (like a Rescue USB's): unlock with your backup's
   password, look inside; then try to delete, add a key and create: all
   must be refused. The throwaway key is removed again at the end.
Nothing in your backup is changed.
"""

import getpass
import json
import os
import subprocess
import sys
import tempfile

from omabackups.core import paths
from omabackups.root import keys
from omabackups.where import ssh
from omabackups.where.server import Gate


def ok(text: str) -> None:
    sys.stderr.write(f"  OK   {text}\n")


def bad(text: str) -> None:
    sys.stderr.write(f"  FAIL {text}\n")


def main() -> int:
    if os.geteuid() != 0:
        sys.stderr.write("Run it with sudo (it uses this computer's root-only keys).\n")
        return 1
    try:
        server = json.loads(paths.server_file().read_text())
    except FileNotFoundError:
        sys.stderr.write("No backup server is set up on this computer yet.\n"
                         "Run 'omabackups setup server' first, then this check.\n")
        return 1
    gate, bid = Gate(server["address"]), server["backup"]
    failures = 0

    sys.stderr.write("\n1. This computer's key\n")
    gate.check_version()
    ok("the gatekeeper answers, version 1")
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    ok(f"unlocked with this computer's key (hold {hold[:6]}...)")
    inside = gate.call("points", bid)
    ok(f"looked inside: line {inside['lines'][0]['line']}, {len(inside['points'])} restore points")
    space = gate.call("space", bid)
    ok(f"space: box {space['box'] >> 30} GiB, store has {space['store_free'] >> 30} GiB free")
    gate.call("lock", bid)
    ok("locked")

    sys.stderr.write("\n2. A throwaway rescue key\n")
    with tempfile.TemporaryDirectory() as tmp:
        key = os.path.join(tmp, "rescue")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
        pub = " ".join(open(key + ".pub").read().split()[:2])
        rid = gate.call("add-key", bid, "throwaway-check", data=pub.encode())["key"]
        ok("added a rescue key")
        # Its own connection (never this computer's shared one), its own key.
        rescue = [key if x == str(paths.keys_dir() / "ssh_key")
                  else "ControlMaster=no" if x.startswith("ControlMaster=")
                  else "ControlPath=none" if x.startswith("ControlPath=")
                  else x for x in ssh.as_gatekeeper(server["address"])]
        try:
            def as_rescue(command, data=b""):
                return subprocess.run([*rescue, command], input=data, capture_output=True)

            password = getpass.getpass("  Your backup's password (to test the rescue key): ")
            done = as_rescue(f"unlock {bid}", password.encode())
            (ok if done.returncode == 0 else bad)("rescue key unlocks with the password")
            failures += done.returncode != 0
            done = as_rescue(f"points {bid}")
            (ok if done.returncode == 0 else bad)("rescue key can look inside")
            failures += done.returncode != 0
            for command in (f"delete {bid} 001-2026-01-01-0000", f"add-key {bid} more",
                            "create 2147483648"):
                done = as_rescue(command, pub.encode())
                refused = done.returncode == 1
                (ok if refused else bad)(f"refused: {command.split()[0]} "
                                         f"({done.stderr.decode().strip().removeprefix('omabackups-gate: ')})")
                failures += not refused
        finally:
            gate.call("lock", bid)
            gate.call("remove-key", bid, rid)
            ok("locked, and the throwaway key removed")

    sys.stderr.write("\nAll good.\n" if not failures else f"\n{failures} check(s) failed.\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
