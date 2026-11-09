"""Root jobs for Migrate (6.1 F, D22a), as root, through the gatekeeper.

migrate-join      connect to a backup on a server with its password: this
                  computer gets its own key file there and may read it; only
                  then is the server recorded (as "migrating", no line yet)
migrate-points    the restore points there
migrate-info      a restore point's list of changes (changes.json)
migrate-settings  bring the ticked settings and System tweaks back from a
                  restore point, in 1.x's order (migrate/apply.py): fetch
                  all, let go of the backup, services swapped in and switched
                  on as they were, your units on, the old user name fixed
"""

import base64
import json
import os
import pwd
import subprocess
import time
from pathlib import Path

from omabackups.backup import run
from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic
from omabackups.migrate import apply
from omabackups.root import keys
from omabackups.root.job_server import ADDRESS, HOST_KEY
from omabackups.where import location
from omabackups.where.server import Gate

GATE_NEEDED = 13          # join and handover
POINT = run.thinning.NAME


def _gate_ok(gate) -> dict:
    version = gate.check_version()
    if version.get("gate", 0) < GATE_NEEDED:
        raise OmaError("OmaBackups on your backup server needs updating before you can Migrate.",
                       "On the old computer: omabackups setup server --update. Then try again.",
                       json.dumps(version), code="gate-version")
    return version


def join(request: dict) -> dict:
    address, host_keys, password = (str(request.get("address", "")), request.get("host_keys"),
                                    request.get("password"))
    if not ADDRESS.match(address):
        raise OmaError("That server address can't be used.", "Check it and try again.",
                       address, code="bad-request")
    if not isinstance(host_keys, list) or not host_keys or not all(
            isinstance(k, str) and HOST_KEY.match(k) for k in host_keys):
        raise OmaError("The server's identity (host key) is missing.", "Run Migrate again.",
                       code="bad-request")
    if not isinstance(password, str) or not password:
        raise OmaError("Your backup's password is missing.", code="bad-request")
    try:
        current = json.loads(paths.server_file().read_text())
    except (OSError, ValueError):
        current = {}
    if current and not current.get("migrating"):
        raise OmaError("This computer already backs up somewhere.",
                       "Start over first (Settings › Your backup), then Migrate.", code="already-set-up")
    write_atomic(paths.known_hosts_file(), ("\n".join(host_keys) + "\n").encode(), 0o644)
    gate = Gate(address)
    version = _gate_ok(gate)
    secrets = json.dumps({"password": password,
                          "key": base64.b64encode(keys.read_unlock_key()).decode()})
    found = gate.call("join", data=secrets.encode())["backups"]
    chosen = request.get("backup")
    if len(found) > 1 and chosen not in [b["id"] for b in found]:
        return {"choose": found}
    bid = chosen or found[0]["id"]
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]   # this computer's own key now
    try:
        inside = gate.call("points", bid)
    finally:
        gate.call("lock", bid, hold)
    server = {"address": address, "backup": bid, "line": None, "migrating": True,
              "gate": version["gate"], "set_up": int(time.time())}
    write_atomic(paths.server_file(), (json.dumps(server, indent=2) + "\n").encode(), 0o644)
    run.pause_automatic("Migrate")
    run.save_record({**run.load_record(), "all_points": inside["points"],
                     "kept": inside["kept"].get("kept", []), "return_point": inside["kept"].get("return_point")})
    return {"backup": bid, "points": inside["points"], "lines": inside["lines"],
            "owner": inside["owner"], "kept": inside["kept"]}


def _open():
    server = location.load()
    gate, _away = location.connect(server)
    _gate_ok(gate)
    return gate, server["backup"]


def points(request: dict) -> dict:
    """The restore points to start from (Run Migrate again, or after a join)."""
    gate, bid = _open()
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    try:
        inside = gate.call("points", bid)
    finally:
        gate.call("lock", bid, hold)
    return {"backup": bid, "points": inside["points"], "lines": inside["lines"],
            "owner": inside["owner"], "kept": inside["kept"]}


def info(request: dict) -> dict:
    point = str(request.get("point", ""))
    if not POINT.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    gate, bid = _open()
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    try:
        return gate.call("info", bid, point)
    finally:
        gate.call("lock", bid, hold)


def _clean(paths_: list, absolute: bool) -> list[str]:
    out = []
    for p in paths_ if isinstance(paths_, list) else []:
        p = str(p)
        if absolute and not p.startswith("/"):
            continue
        parts = [x for x in p.lstrip("/").split("/") if x]
        if parts and ".." not in parts and "\n" not in p:
            out.append("/".join(parts))
    return out


def _fetch(gate, bid: str, point: str, part: str, items: list[str], dest: Path, chown: str) -> str:
    """rsync just these paths (relative to the part) into dest; the error text if any."""
    if not items:
        return ""
    dest.mkdir(parents=True, exist_ok=True)
    command = ["rsync", "-aHAX", "-r", "--files-from=-", "--from0", *chown.split(),
               "-e", gate.rsh(), f"--rsync-path=fetch {bid} {point} {part}",
               f"{gate.rsync_target()}:{part}/", f"{dest}/"]
    done = subprocess.run(command, input=b"\0".join(i.encode() for i in items) + b"\0",
                          capture_output=True, env=gate.rsync_env())
    return "" if done.returncode in (0, 24) else done.stderr.decode("utf-8", "replace")[-2000:]


def _merges(asked) -> list[dict]:
    """Keybindings, bar & theme files to merge: only the shapes plan.MERGE makes."""
    from omabackups.migrate import plan
    out = []
    for m in asked if isinstance(asked, list) else []:
        made = plan.merge_kind("~/" + str(m.get("path", ""))) if isinstance(m, dict) else None
        if made and ".." not in made["path"].split("/"):
            out.append(made)
    return out


def settings(request: dict) -> dict:
    """Settings and System tweaks back, in 1.x's order (migrate/apply.py)."""
    point = str(request.get("point", ""))
    if not POINT.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    user = run.linked_user()
    from_user = str(request.get("from_user") or user)
    from omabackups.restore.files import USER
    if not USER.match(from_user):
        raise OmaError("That user name can't be used.", code="bad-request")
    home_items = _clean([str(x).removeprefix("~/") for x in request.get("home", [])], absolute=False)
    system_items = _clean(request.get("system", []), absolute=True)
    logger = log.get("migrate")
    gate, bid = _open()
    server = location.load()
    if server.get("migrating"):          # the handover starts from here (first backup)
        write_atomic(paths.server_file(), (json.dumps({**server, "from_point": point,
                                                       "from_user": from_user}, indent=2)
                                           + "\n").encode(), 0o644)
    if os.environ.get("OMABACKUPS_SYSROOT"):      # tests: the sandbox's home and system
        home, root, owner = Path.home(), Path(os.environ["OMABACKUPS_SYSROOT"]), ""
    else:
        entry = pwd.getpwnam(user)
        home, root = Path(entry.pw_dir), Path("/")
        owner = f"--chown={entry.pw_uid}:{entry.pw_gid} --numeric-ids"
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    keeper = run.HoldKeeper(gate, bid, hold, logger)
    released = []

    def let_go() -> None:
        if not released:
            released.append(True)
            keeper.stop()
            gate.call("lock", bid, hold)

    def get(part: str, items: list[str], dest: Path, owned: bool) -> str:
        return _fetch(gate, bid, point, part, items, dest, owner if owned else "")

    try:
        done = apply.run(get, home, root, from_user, user, home_items, system_items,
                         request.get("units", []), bool(request.get("theme")), let_go,
                         _merges(request.get("merge", [])))
    finally:
        let_go()
    logger.info("migrate settings from %s: %d home, %d system, services %s, %d renamed, %d problems",
                point, len(home_items), len(system_items), done["services"], len(done["renamed"]),
                len(done["problems"]))
    return done
