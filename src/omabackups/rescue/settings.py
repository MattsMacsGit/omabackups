"""A Rescue USB's settings (5.7, D11, D48): where the backup server is (its
address, home and Tailscale addresses), the server's fingerprint, and the
stick's own key, read only on the server: it can list and restore, never
change or delete. No key that opens the backup: every rescue asks for the
backup's password.

One stick at a time (D11): making a new one takes the last one's key off
the server, so a lost stick can always be cut off.

On the stick, the settings are put where a computer keeps its own
(/etc/omabackups/server.json, the key, known_hosts), so the rest of
OmaBackups works there unchanged.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic

SERVER_KEYS = ("kind", "address", "home", "away", "backup", "line")
FILES = ("rescue.json", "server.json", "ssh_key", "known_hosts")
# Where a stick's settings are found: its own small part (9c), or built into
# the image for testing (rescue/iso/build.sh --settings).
PLACES = (Path("/run/omabackups-rescue/settings"), Path("/etc/omabackups-rescue"))


def record_file() -> Path:
    return paths.system_state_dir() / "rescue.json"


def _new_key(folder: Path) -> tuple[str, str]:
    key = folder / "key"
    done = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
                           f"omabackups-rescue-{time.strftime('%Y%m%d')}", "-f", str(key)],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise OmaError("The Rescue USB's key couldn't be made.", "Check that openssh is installed.",
                       done.stderr.strip(), code="no-key")
    private, public = key.read_text(), key.with_suffix(".pub").read_text().split()
    return private, f"{public[0]} {public[1]}"


def make(gate, server: dict) -> dict:
    """Root side: a new stick key on the server (the last one's taken off);
    returns the stick's settings."""
    bid = server["backup"]
    with tempfile.TemporaryDirectory() as tmp:
        private, public = _new_key(Path(tmp))
    label = f"Rescue USB {time.strftime('%Y-%m-%d')}"
    kid = gate.call("add-key", bid, label.replace(" ", "-"), data=public.encode())["key"]
    try:
        old = json.loads(record_file().read_text()).get("key")
    except (OSError, ValueError):
        old = None
    if old and old != kid:
        try:
            gate.call("remove-key", bid, old)
        except OmaError:
            pass            # already gone
    record = {"key": kid, "made": int(time.time()), "computer": socket.gethostname()}
    write_atomic(record_file(), (json.dumps(record) + "\n").encode(), 0o600)
    return {"rescue.json": json.dumps(record, indent=2) + "\n",
            "server.json": json.dumps({k: server[k] for k in SERVER_KEYS if k in server}, indent=2) + "\n",
            "ssh_key": private,
            "known_hosts": paths.known_hosts_file().read_text()}


def write(bundle: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    for name in FILES:
        write_atomic(folder / name, bundle[name].encode(), 0o600)


def _mount_settings_part() -> None:
    """On the stick: its own small settings part (OMABACKUPS), read only."""
    import subprocess
    part = Path("/dev/disk/by-label/OMABACKUPS")
    if part.exists() and not os.path.ismount(PLACES[0]):
        PLACES[0].mkdir(parents=True, exist_ok=True)
        subprocess.run(["mount", "-o", "ro", str(part), str(PLACES[0])], capture_output=True)


def find() -> Path | None:
    _mount_settings_part()
    for place in PLACES:
        if all((place / name).is_file() for name in FILES):
            return place
    return None


def install(folder: Path) -> dict:
    """Stick side: the settings where OmaBackups looks for a computer's own."""
    server = json.loads((folder / "server.json").read_text())
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    write_atomic(paths.server_file(), (json.dumps({**server, "kind": "server"}, indent=2) + "\n").encode(), 0o644)
    paths.keys_dir().mkdir(parents=True, exist_ok=True)
    os.chmod(paths.keys_dir(), 0o700)
    shutil.copyfile(folder / "ssh_key", paths.keys_dir() / "ssh_key")
    os.chmod(paths.keys_dir() / "ssh_key", 0o600)
    shutil.copyfile(folder / "known_hosts", paths.known_hosts_file())
    return json.loads((folder / "rescue.json").read_text())
