"""`omabackups setup server` (BUILD 6.1 C, step 2; D20, D27).

1. Link this computer (pkexec: this computer's password, once).
2. One login to the server (its password, once): copy the gatekeeper over,
   check it arrived intact, install it with the server's sudo (its sudo
   password, once).
3. Choose your backup's password; the root helper creates the backup box
   on the server and proves its key opens it.
4. Only then: this computer is at the next step of setup.
"""

import json
import os
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path

from omabackups.core import flow, ids, paths, rootjob, state
from omabackups.core.errors import OmaError
from omabackups.setup import bundle, menu
from omabackups.where import ssh


def link() -> str:
    """Returns this computer's public key (making the keys if needed)."""
    if os.environ.get("OMABACKUPS_SYSROOT"):
        command = [sys.executable, "-m", "omabackups", "--json", "link"]   # tests
    else:
        command = ["pkexec", "/usr/bin/omabackups", "--json", "link"]
    done = subprocess.run(command, stdout=subprocess.PIPE, text=True)
    if done.returncode in (126, 127):
        raise OmaError("This computer's password wasn't given, so nothing was set up.",
                       "Run setup again when you're ready.", code="cancelled")
    if done.returncode == 0:
        from omabackups.setup import udiskie
        if note := udiskie.install():          # audit 7.4: our disks are just listed when plugged in
            from omabackups.core import log
            log.get("setup").info(note)
    try:
        return json.loads(done.stdout.splitlines()[-1])["public_key"]
    except (ValueError, IndexError, KeyError):
        raise OmaError("Linking this computer to OmaBackups didn't work.",
                       "Try again. If it keeps failing, report it with the details.",
                       done.stdout.strip() or f"exit {done.returncode}", code="link-failed") from None


def public_key() -> str:
    """This computer's SSH public key (readable by everyone, made by link)."""
    try:
        text = paths.public_key_file().read_text().split()
        return f"{text[0]} {text[1]}"
    except (OSError, IndexError):
        return link()   # not there yet: link makes or finds it (as root)


def label() -> str:
    host = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:40] or "computer"
    return f"{host} ({ids.short(ids.system_id())})"


class Login:
    """The user's own SSH login on the server, shared by every step of setup."""

    def __init__(self, address: str, user: str):
        self.known_hosts = paths.runtime_dir() / "setup_known_hosts"
        self.base = ssh.as_user(address, user, self.known_hosts)
        self.base[1:1] = ["-o", "HashKnownHosts=no"]
        # Setup's own list lives in /run and is gone after a restart, so a
        # `setup server --update` asked to confirm the server's key again.
        # The backups' list already knows it: read both, write only setup's.
        system = paths.known_hosts_file()
        if system.is_file() and " " not in f"{system}{self.known_hosts}":
            mine = f"UserKnownHostsFile={self.known_hosts}"
            self.base = [f"{mine} {system}" if x == mine else x for x in self.base]
        # Keep the login open while the user reads the server's disk list.
        self.base = [x if x != "ControlPersist=60" else "ControlPersist=900" for x in self.base]

    def run(self, command: str, data: bytes | None = None, terminal: bool = False):
        if terminal:   # sudo asks for its password on the terminal
            return subprocess.run([*self.base[:1], "-t", "-q", *self.base[1:], command])
        return subprocess.run([*self.base, command], input=data, capture_output=True)

    def places(self) -> list:
        """D30: every disk on the server, with its free space and what's on it.
        The first call logs in: the server password is asked here."""
        from omabackups.setup import disks, places
        listed = self.run(f"lsblk -J -b -e7 -o {places.COLUMNS}")
        if listed.returncode == 255:
            raise _failed("Couldn't log in to your backup server.", listed)
        system = self.run('lsblk -J -s -o NAME,PATH,TYPE "$(findmnt -n -o SOURCE / | sed "s/\\[.*//")"')
        known = self.run("cat /etc/omabackups-gate/gate.json 2>/dev/null")
        try:
            store = json.loads(known.stdout or b"{}").get("store", "")
        except ValueError:
            store = ""
        try:
            return places.places(json.loads(listed.stdout), disks.disks_in(json.loads(system.stdout)),
                                 store)
        except ValueError:
            raise _failed("Couldn't read the list of disks on your backup server.", listed,
                          "Check that the server has lsblk (util-linux), then try again.") from None

    def close(self) -> None:
        subprocess.run([*self.base[:1], "-O", "exit", *self.base[1:]], capture_output=True)

    def host_keys(self) -> list[str]:
        try:
            lines = self.known_hosts.read_text().splitlines()
        except OSError:
            return []
        return [x for x in lines if x.startswith(paths.SERVER_ALIAS + " ")]


def _failed(what: str, done, todo: str = "Check the address and your login, then try again.") -> OmaError:
    details = done.stderr.decode("utf-8", "replace").strip() if done.stderr else ""
    return OmaError(what, todo, details or f"exit {done.returncode}", code="setup-server")


def install(login: Login, store: str, pub: str) -> dict:
    gate = bundle.gate_file()
    say = sys.stderr.write
    done = login.run("command -v python3 >/dev/null && command -v sudo >/dev/null && "
                     "command -v systemctl >/dev/null && mktemp -d")
    if done.returncode == 255:
        raise _failed("Couldn't log in to your backup server.", done)
    if done.returncode != 0:
        raise _failed("Your backup server is missing python3, sudo or systemd, which OmaBackups needs.",
                      done, "Install them on the server, then run setup again.")
    folder = done.stdout.decode().strip()
    q = shlex.quote
    for name, data in (("gate.pyz", gate.read_bytes()), ("key.pub", (pub + "\n").encode())):
        sent = login.run(f"cat > {q(folder)}/{name}", data=data)
        if sent.returncode != 0:
            raise _failed("Couldn't copy OmaBackups to your backup server.", sent)

    menu.title("Setting up OmaBackups on the server",
               "The server asks for your password again: sudo needs it to install\n"
               "OmaBackups there and prepare the disk.")
    command = (f"sudo python3 {q(folder)}/gate.pyz install {q(store)} {q(ids.system_id())} "
               f"{q(label())} {bundle.sha256(gate)} {q(folder)}/key.pub > {q(folder)}/result.json")
    login.run(command, terminal=True)
    done = login.run(f"cat {q(folder)}/result.json; rm -rf {q(folder)}")
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise OmaError("Setting up OmaBackups on your backup server didn't finish.",
                       "Read the messages above for why, fix that, then run setup again.",
                       done.stderr.decode("utf-8", "replace").strip(), code="setup-server") from None


def create(address: str, host_keys: list[str], size: int, password: str) -> dict:
    answer = rootjob.run("create-backup", {"address": address, "host_keys": host_keys,
                                           "size": size, "password": password})
    # Written only now: the backup exists and opens with this computer's key.
    state.write(flow.SETUP, {"where": "server", "first_backup": False})
    return answer


def check_store(path: str) -> str:
    if not path.startswith("/") or "\n" in path or len(path) > 200:
        raise OmaError("The folder on the server must be a full path, like /srv/backups/omabackups.",
                       code="bad-folder")
    return str(Path(path))
