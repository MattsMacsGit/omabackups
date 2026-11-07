"""Stage 3's check on real backups: is the latest restore point an exact copy?

Run on the computer as root, after at least one backup:
    sudo python3 tests/live/backup_check.py

For system and home it compares the latest restore point on the server,
byte by byte (rsync --checksum, dry run: nothing is changed anywhere), with
the snapshot on this computer that it was made from. Skipped things are left
out of the comparison. Expect: no differences.
"""

import json
import os
import shlex
import subprocess
import sys

from omabackups.backup import run, skips
from omabackups.backup.source import Snapshots, parts
from omabackups.core import paths
from omabackups.root import keys
from omabackups.where import ssh
from omabackups.where.server import Gate


def main() -> int:
    if os.geteuid() != 0:
        sys.stderr.write("Run it with sudo (it reads this computer's snapshots and root-only keys).\n")
        return 1
    record = run.load_record()
    if not record.get("last_point"):
        sys.stderr.write("No backup has finished yet: run 'omabackups backup' first.\n")
        return 1
    server = json.loads(paths.server_file().read_text())
    gate, bid, point = Gate(server["address"]), server["backup"], record["last_point"]
    sys.stderr.write(f"\nComparing restore point {point} with this computer's snapshots...\n")
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    failures = 0
    try:
        for part in parts():
            if not part.btrfs:
                continue
            with Snapshots(part.device) as snaps:
                local = snaps.path(record["since"][part.name])
                done = subprocess.run(
                    ["rsync", "-n", "-c", "-aHAX", "--numeric-ids", "--delete", "--itemize-changes",
                     *skips.for_part(part.name).rsync_rules(),
                     "-e", shlex.join(ssh.gatekeeper_ssh()),
                     f"--rsync-path=fetch {bid} {point} {part.name}",
                     f"{ssh.target(server['address'])}:x/", f"{local}/"],
                    capture_output=True, text=True)
                # The top folder's own date may differ (it's a snapshot), and so may
                # the empty placeholder a snapshot shows for another subvolume
                # inside it (btrfs gives those inode 2 and a new date every time).
                def placeholder(line: str) -> bool:
                    if not line.startswith(".d..t...... "):
                        return False
                    try:
                        return os.lstat(local / line[12:].rstrip("/")).st_ino == 2
                    except OSError:
                        return False
                diffs = [x for x in done.stdout.splitlines()
                         if x and x != ".d..t...... ./" and not placeholder(x)]
                if done.returncode not in (0, 24) or diffs:
                    failures += 1
                    sys.stderr.write(f"  FAIL {part.name}: {len(diffs)} differences "
                                     f"(rsync exit {done.returncode})\n")
                    for line in diffs[:15]:
                        sys.stderr.write(f"         {line}\n")
                    if done.stderr.strip():
                        sys.stderr.write(f"         {done.stderr.strip()[-500:]}\n")
                else:
                    sys.stderr.write(f"  OK   {part.name}: identical, byte for byte\n")
    finally:
        gate.call("lock", bid, hold)
    sys.stderr.write("\nAll good.\n" if not failures else f"\n{failures} part(s) differ.\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
