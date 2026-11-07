"""SSH to the backup server: one shared connection per job, our own key and
our own known-hosts file, the host key filed under one fixed name (so the
home address and the away address check the same key, D17).
chacha20 is OpenSSH's default and the fastest on a Pi (D25): left as is.
"""

import os
from pathlib import Path

from omabackups.core import paths

ACCOUNT = "omabackups-gate"


def common(control_dir: Path) -> list[str]:
    return [
        "-o", f"HostKeyAlias={paths.SERVER_ALIAS}",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={control_dir}/ssh-%C",
        "-o", "ControlPersist=60",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=4",
        "-o", "ConnectTimeout=15",
    ]


def as_gatekeeper(address: str) -> list[str]:
    """The root jobs' SSH: this computer's key, to the gatekeeper account."""
    control = paths.system_run_dir()
    control.mkdir(parents=True, exist_ok=True)
    return ["ssh", "-T", "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes", "-i", str(paths.keys_dir() / "ssh_key"),
            "-o", f"UserKnownHostsFile={paths.known_hosts_file()}",
            "-o", "StrictHostKeyChecking=yes", "-o", "GlobalKnownHostsFile=/dev/null",
            *common(control), f"{ACCOUNT}@{address}"]


def as_user(address: str, login: str, known_hosts: Path) -> list[str]:
    """Setup's SSH: the user's own login on the server, typed passwords. A new
    server's host key is shown and asked about by ssh itself, then kept in
    `known_hosts` for the root jobs."""
    control = paths.runtime_dir()
    control.mkdir(parents=True, exist_ok=True)
    os.chmod(control, 0o700)
    return ["ssh", "-o", f"UserKnownHostsFile={known_hosts}",
            "-o", "StrictHostKeyChecking=ask", "-o", "GlobalKnownHostsFile=/dev/null",
            *common(control), f"{login}@{address}"]
