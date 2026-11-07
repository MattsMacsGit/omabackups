"""Stands in for `ssh omabackups-gate@server` in tests (rsync's -e program).

rsync runs: fake_ssh.py HOST <remote command words...>. Like sshd with a
forced command, this puts the remote command in SSH_ORIGINAL_COMMAND and runs
the gatekeeper's relay for the key in OMABACKUPS_TEST_KEY.
"""

import os
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "server" / "gate"

os.environ["SSH_ORIGINAL_COMMAND"] = " ".join(sys.argv[2:])
os.execv(sys.executable, [sys.executable, str(GATE), "client", os.environ["OMABACKUPS_TEST_KEY"]])
