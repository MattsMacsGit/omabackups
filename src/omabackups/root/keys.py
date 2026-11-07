"""This computer's root-only keys (BUILD 5.4):
- ssh_key: logs in to the backup server's gatekeeper (ed25519);
- unlock_key: opens the backup with no typing (a second way in besides
  the backup's password, which stays the only way in from a Rescue USB).
"""

import os
import secrets
import subprocess

from omabackups.core import ids, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic


def ssh_key():
    return paths.keys_dir() / "ssh_key"


def unlock_key():
    return paths.keys_dir() / "unlock_key"


def ensure() -> str:
    """Make the keys if they aren't there yet; return the SSH public key."""
    folder = paths.keys_dir()
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    if not ssh_key().exists():
        tmp = folder / ".ssh_key.new"
        for leftover in (tmp, tmp.with_name(".ssh_key.new.pub")):
            leftover.unlink(missing_ok=True)
        done = subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
             f"omabackups-{ids.short(ids.system_id())}", "-f", str(tmp)],
            capture_output=True, text=True)
        if done.returncode != 0:
            raise OmaError("OmaBackups couldn't make this computer's key.",
                           "Check that openssh is installed, then try again.",
                           done.stderr.strip(), code="no-key")
        os.replace(tmp.with_name(".ssh_key.new.pub"), folder / "ssh_key.pub")
        os.replace(tmp, ssh_key())
    if not unlock_key().exists():
        write_atomic(unlock_key(), secrets.token_bytes(64), 0o600)
    return public_key()


def public_key() -> str:
    text = (paths.keys_dir() / "ssh_key.pub").read_text(encoding="ascii").split()
    return f"{text[0]} {text[1]}"


def read_unlock_key() -> bytes:
    return unlock_key().read_bytes()
