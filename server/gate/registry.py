"""Who may do what: the keys, the backups, and each key's role on each backup.

Kept by root in one JSON file. The account's authorized_keys file is written
from it (root-owned, so the account can't change it): every key may only run
the relay, and the relay only reaches this gatekeeper.
"""

import base64
import fcntl
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import conf

FORMAT = 1


class Refused(Exception):
    """A request the gatekeeper won't do; the message goes back to the caller."""


def key_id(pubkey: str) -> str:
    blob = base64.b64decode(pubkey.split()[1])
    return hashlib.sha256(blob).hexdigest()[:16]


def _write_atomic(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@contextmanager
def changing():
    """Load, let the caller change, save: one change at a time."""
    conf.RUN.mkdir(parents=True, exist_ok=True)
    fd = os.open(conf.RUN / "registry.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        data = load()
        yield data
        save(data)
    finally:
        os.close(fd)


def load() -> dict:
    try:
        data = json.loads(conf.REGISTRY.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"format": FORMAT, "keys": {}, "backups": {}}
    if data.get("format") != FORMAT:
        raise Refused(f"the registry is format {data.get('format')}, this gatekeeper reads {FORMAT}")
    return data


def save(data: dict) -> None:
    _write_atomic(conf.REGISTRY, json.dumps(data, indent=2, sort_keys=True) + "\n", 0o600)
    write_authorized_keys(data)


def write_authorized_keys(data: dict) -> None:
    lines = ["# Written by the OmaBackups gatekeeper. Every key can only reach the gatekeeper."]
    for kid, key in sorted(data["keys"].items()):
        command = f"/usr/bin/python3 {conf.INSTALLED} client {kid}"
        lines.append(f'restrict,command="{command}" {key["pub"]} omabackups-{key["kind"]}-{kid}')
    conf.AUTHORIZED_KEYS.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(conf.AUTHORIZED_KEYS, "\n".join(lines) + "\n", 0o644)


def add_key(data: dict, pub: str, kind: str, label: str, system: str = "") -> str:
    pub = pub.strip()
    if not conf.PUBKEY.match(pub):
        raise Refused("that is not an ssh-ed25519 public key")
    if not conf.LABEL.match(label):
        raise Refused("the key's label has characters it can't have")
    if kind not in ("computer", "rescue"):
        raise Refused("a key is for a computer or a Rescue USB")
    if system and not conf.SYSTEM_ID.match(system):
        raise Refused("that is not a system ID")
    kid = key_id(pub)
    data["keys"][kid] = {"pub": pub, "kind": kind, "label": label, "system": system,
                         "added": int(time.time())}
    return kid


def remove_key(data: dict, kid: str) -> None:
    data["keys"].pop(kid, None)
    for backup in data["backups"].values():
        backup["roles"].pop(kid, None)


def the_key(data: dict, kid: str) -> dict:
    if not conf.KEY_ID.match(kid or "") or kid not in data["keys"]:
        raise Refused("this key isn't known here")
    return data["keys"][kid]


def the_backup(data: dict, bid: str, kid: str, allowed: tuple) -> dict:
    """The backup, if this key has one of the `allowed` roles on it.
    A backup the key may not touch looks exactly like one that doesn't exist."""
    if not conf.BACKUP_ID.match(bid or ""):
        raise Refused("that is not a backup ID")
    backup = data["backups"].get(bid)
    role = backup["roles"].get(kid) if backup else None
    if role is None:
        raise Refused("no such backup")
    if role not in allowed:
        raise Refused(f"a {role} key can't do that")
    return backup


def mine(data: dict, kid: str) -> dict:
    """Every backup this key has a role on: {backup id: role}."""
    return {bid: b["roles"][kid] for bid, b in data["backups"].items() if kid in b["roles"]}
