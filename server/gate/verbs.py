"""The gatekeeper's fixed list of actions (BUILD 5.3), and who may do each.

Roles per backup: owner (everything) and rescue (unlock with the typed
password, look, restore: never change or delete). A backup a key has no
role on answers exactly like one that doesn't exist.
Stage 2 verbs; the data verbs (snapshot, send, fetch, reuse...) come with
the backups themselves (stage 3).
"""

import base64
import binascii
import json
import time
from pathlib import Path

import conf
import holds
import layout
import registry
from host import host, mountpoint
from registry import Refused

ANY = conf.ROLES
OWNER = ("owner",)


class Call:
    def __init__(self, kid: str, args: list[str], reader):
        self.kid = kid
        self.args = args
        self.reader = reader   # wire.Reader: the caller's input

    def read_input(self, limit: int) -> bytes:
        """All the input, up to its end (at most limit + 1 bytes)."""
        return self.reader.upto(limit)

    def secret(self) -> bytes:
        data = self.read_input(conf.MAX_SECRET + 1)
        if not data or len(data) > conf.MAX_SECRET:
            raise Refused("the password or key is missing or too long")
        return data


def _argc(call: Call, *counts: int) -> None:
    if len(call.args) not in counts:
        raise Refused("wrong number of arguments")


def store() -> Path:
    try:
        settings = json.loads(conf.SETTINGS.read_text(encoding="utf-8"))
        return Path(settings["store"])
    except (OSError, ValueError, KeyError):
        raise Refused("this server has no backup store set up yet") from None


def _box(bid: str) -> Path:
    return store() / f"{bid}.box"


def _need_open(bid: str) -> Path:
    if not host().is_mounted(bid):
        raise Refused("this backup is locked (unlock it first)")
    inside = mountpoint(bid)
    layout.check(inside, bid)
    return inside


# --- verbs any known key may use --------------------------------------------

def v_version(call: Call) -> dict:
    _argc(call, 0)
    return {"gate": conf.VERSION, "contract": conf.CONTRACT}


def v_status(call: Call) -> dict:
    _argc(call, 0)
    data = registry.load()
    key = registry.the_key(data, call.kid)
    out = []
    for bid, role in sorted(registry.mine(data, call.kid).items()):
        b = data["backups"][bid]
        out.append({"id": bid, "role": role, "open": host().is_mounted(bid), "size": b["size"],
                    "created": b["created"], "cipher": b["cipher"]})
    return {"key": {"id": call.kid, "kind": key["kind"], "label": key["label"]}, "backups": out}


def v_addresses(call: Call) -> dict:
    """This server's addresses, so a computer can still reach it away from home
    (its Tailscale address and name, if it has one: D17)."""
    _argc(call, 0)
    registry.the_key(registry.load(), call.kid)
    import ipaddress
    import shutil
    import subprocess
    found, tailscale = [], {}
    done = subprocess.run(["ip", "-j", "addr"], capture_output=True, text=True)
    try:
        for link in json.loads(done.stdout or "[]"):
            for a in link.get("addr_info", []):
                ip = ipaddress.ip_address(a["local"])
                if not (ip.is_loopback or ip.is_link_local):
                    found.append(str(ip))
    except (ValueError, KeyError, TypeError):
        pass
    if shutil.which("tailscale"):
        done = subprocess.run(["tailscale", "status", "--json", "--self=true", "--peers=false"],
                              capture_output=True, text=True, timeout=10)
        try:
            me = json.loads(done.stdout)["Self"]
            tailscale = {"ips": me.get("TailscaleIPs", []), "name": me.get("DNSName", "").rstrip(".")}
        except (ValueError, KeyError, TypeError):
            pass
    return {"addresses": found, "tailscale": tailscale}


# --- making a backup ---------------------------------------------------------

def v_create(call: Call) -> dict:
    """create SIZE -- a new backup box, owned by this computer. Input (JSON):
    {"password": the backup's password, "key": this computer's key file, base64}."""
    _argc(call, 1)
    try:
        size = int(call.args[0])
    except ValueError:
        raise Refused("the size must be a number of bytes") from None
    if size < conf.MIN_BOX:
        raise Refused("a backup box must be at least 1 GiB")
    data = registry.load()
    key = registry.the_key(data, call.kid)
    if key["kind"] != "computer":
        raise Refused("only a computer's key can create a backup")
    try:
        given = json.loads(call.read_input(4 * conf.MAX_SECRET))
        password = given["password"].encode("utf-8")
        machine_key = base64.b64decode(given["key"], validate=True)
    except (ValueError, KeyError, TypeError, AttributeError, binascii.Error):
        raise Refused("create needs the password and the key") from None
    if not password or not machine_key or len(password) > conf.MAX_SECRET:
        raise Refused("create needs the password and the key")

    folder = store()
    h = host()
    if size > h.store_free(folder):
        raise Refused(f"the backup store has only {h.store_free(folder) >> 30} GiB free")
    bid = registry_new_id(data)
    box = folder / f"{bid}.box"
    with holds.turn(bid):
        cipher = h.create(box, size, password, machine_key, bid)
        try:
            layout.make(mountpoint(bid), bid, key["system"], h)
        except BaseException:
            h.remove_box(box, bid)
            raise
        h.close(bid)
    # Registered only after the box was made, filled and locked again.
    with registry.changing() as data:
        data["backups"][bid] = {"size": size, "cipher": cipher, "created": int(time.time()),
                                "roles": {call.kid: "owner"}}
    return {"id": bid, "cipher": cipher, "size": size}


def registry_new_id(data: dict) -> str:
    from host import new_backup_id
    while (bid := new_backup_id()) in data["backups"]:
        pass
    return bid


# --- unlock / hold / lock (1.x's lessons: see holds.py) ----------------------

def v_unlock(call: Call) -> dict:
    """unlock BACKUP -- input: this computer's key file, or the backup's password."""
    _argc(call, 1)
    bid = call.args[0]
    registry.the_backup(registry.load(), bid, call.kid, ANY)
    # Read the secret before taking the turn, and every time (1.x lesson).
    secret = call.secret()
    started = time.time()
    with holds.turn(bid):
        host().open(_box(bid), bid, secret)
        layout.check(mountpoint(bid), bid)
        if holds.lock_wanted_since(bid, started):
            holds.drop_all(bid)
            host().close(bid)
            raise Refused("the backup was locked while this was opening; try again")
        hid = holds.add(bid)
    return {"hold": hid}


def v_hold(call: Call) -> dict:
    """hold BACKUP HOLD -- still here (long jobs say this as they go)."""
    _argc(call, 2)
    bid, hid = call.args
    registry.the_backup(registry.load(), bid, call.kid, ANY)
    if not conf.HOLD_ID.match(hid) or not holds.refresh(bid, hid):
        raise Refused("that hold has gone; unlock again")
    return {"hold": hid}


def v_lock(call: Call) -> dict:
    """lock BACKUP [HOLD] -- let go of one hold, or with no hold: everyone off, now."""
    _argc(call, 1, 2)
    bid = call.args[0]
    registry.the_backup(registry.load(), bid, call.kid, ANY)
    hid = call.args[1] if len(call.args) == 2 else ""
    if hid and not conf.HOLD_ID.match(hid):
        raise Refused("that is not a hold")
    if not hid:
        holds.want_lock(bid)
    with holds.turn(bid):
        if hid:
            holds.drop(bid, hid)
            left = holds.live(bid)
            if left:
                return {"locked": False, "holds": len(left)}
            # Nobody left: the sweep locks it after the quiet time.
            holds.reset_quiet(bid)
            return {"locked": False, "holds": 0}
        holds.drop_all(bid)
        host().close(bid)
        holds.clear_wanted(bid)
    return {"locked": True, "holds": 0}


# --- looking inside ----------------------------------------------------------

def v_points(call: Call) -> dict:
    _argc(call, 1)
    bid = call.args[0]
    registry.the_backup(registry.load(), bid, call.kid, ANY)
    inside = _need_open(bid)
    return {"points": layout.points(inside), "kept": layout.kept(inside),
            "owner": layout.owner(inside), "lines": layout.lines(inside)}


def v_space(call: Call) -> dict:
    _argc(call, 1)
    bid = call.args[0]
    backup = registry.the_backup(registry.load(), bid, call.kid, ANY)
    answer = {"box": backup["size"], "store_free": host().store_free(store())}
    if host().is_mounted(bid):
        answer["used"], answer["free"] = host().used_inside(bid)
    return answer


# --- changes only an owner may make ------------------------------------------

def v_delete(call: Call) -> dict:
    """delete BACKUP POINT -- never the newest of its line, never a kept one."""
    _argc(call, 2)
    bid, point = call.args
    registry.the_backup(registry.load(), bid, call.kid, OWNER)
    if not conf.POINT.match(point):
        raise Refused("that is not a restore point name")
    with holds.turn(bid):
        inside = _need_open(bid)
        names = layout.points(inside)
        if point not in names:
            raise Refused("no such restore point")
        if point == layout.newest_in_line(names, point[:3]):
            raise Refused("the newest restore point is never deleted")
        kept = layout.kept(inside)
        if point in kept["kept"] or point == kept["return_point"]:
            raise Refused("that restore point is kept; release it first")
        host().delete_subvolume(inside / "points" / point)
    return {"deleted": point}


def v_add_key(call: Call) -> dict:
    """add-key BACKUP LABEL -- a Rescue USB's key (input: its public key), read only."""
    _argc(call, 2)
    bid, label = call.args
    pub = call.read_input(conf.MAX_SECRET).decode("ascii", "replace")
    with registry.changing() as data:
        registry.the_backup(data, bid, call.kid, OWNER)
        kid = registry.add_key(data, pub, "rescue", label)
        if kid == call.kid:
            raise Refused("that is this computer's own key")
        data["backups"][bid]["roles"][kid] = "rescue"
    return {"key": kid, "role": "rescue"}


def v_remove_key(call: Call) -> dict:
    """remove-key BACKUP KEY -- take a Rescue USB's key off this backup."""
    _argc(call, 2)
    bid, kid = call.args
    with registry.changing() as data:
        backup = registry.the_backup(data, bid, call.kid, OWNER)
        if backup["roles"].get(kid) != "rescue":
            raise Refused("that is not a rescue key of this backup")
        del backup["roles"][kid]
        if not registry.mine(data, kid):
            registry.remove_key(data, kid)
    return {"removed": kid}


VERBS = {
    "version": v_version, "status": v_status, "addresses": v_addresses, "create": v_create,
    "unlock": v_unlock, "hold": v_hold, "lock": v_lock,
    "points": v_points, "space": v_space, "delete": v_delete,
    "add-key": v_add_key, "remove-key": v_remove_key,
}


def sweep() -> list[str]:
    """From a timer, as root: lock every backup nobody holds that's been quiet."""
    locked = []
    try:
        names = [p.name for p in (conf.RUN / "boxes").iterdir()]
    except FileNotFoundError:
        return locked
    for bid in names:
        if not conf.BACKUP_ID.match(bid):
            continue
        with holds.turn(bid):
            h = host()
            if not h.is_open(bid):
                continue
            if holds.live(bid):
                holds.reset_quiet(bid)
                continue
            if holds.quiet_long_enough(bid, h.activity(bid)):
                h.close(bid)
                holds.reset_quiet(bid)
                locked.append(bid)
    return locked
