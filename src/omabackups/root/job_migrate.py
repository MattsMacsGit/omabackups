"""Root jobs for Migrate (6.1 F, D22a), as root, through the gatekeeper.

migrate-join      connect to a backup on a server with its password: this
                  computer gets its own key file there and may read it; only
                  then is the server recorded (as "migrating", no line yet)
migrate-points    the restore points there
migrate-info      a restore point's list of changes (changes.json)
migrate-settings  bring the ticked settings and System tweaks back from a
                  restore point: home ones into this user's folder (whatever
                  the old user was called), system ones into place; then the
                  tweaks' units are switched on
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
    command = ["rsync", "-aHAX", "-r", "--files-from=-", "--from0", *chown.split(),
               "-e", gate.rsh(), f"--rsync-path=fetch {bid} {point} {part}",
               f"{gate.rsync_target()}:{part}/", f"{dest}/"]
    done = subprocess.run(command, input=b"\0".join(i.encode() for i in items) + b"\0",
                          capture_output=True, env=gate.rsync_env())
    return "" if done.returncode in (0, 24) else done.stderr.decode("utf-8", "replace")[-2000:]


def settings(request: dict) -> dict:
    point = str(request.get("point", ""))
    if not POINT.match(point):
        raise OmaError("That isn't a restore point.", code="bad-request")
    user = run.linked_user()
    from_user = str(request.get("from_user") or user)
    home_items = _clean([str(x).removeprefix("~/") for x in request.get("home", [])], absolute=False)
    system_items = _clean(request.get("system", []), absolute=True)
    logger = log.get("migrate")
    gate, bid = _open()
    server = location.load()
    if server.get("migrating"):          # the handover starts from here (first backup)
        write_atomic(paths.server_file(), (json.dumps({**server, "from_point": point}, indent=2)
                                           + "\n").encode(), 0o644)
    hold = gate.call("unlock", bid, data=keys.read_unlock_key())["hold"]
    keeper = run.HoldKeeper(gate, bid, hold, logger)
    problems = []
    try:
        if os.environ.get("OMABACKUPS_SYSROOT"):      # tests: the sandbox's home and system
            home, root, chown = Path.home(), Path(os.environ["OMABACKUPS_SYSROOT"]), ""
        else:
            entry = pwd.getpwnam(user)
            home, root = Path(entry.pw_dir), Path("/")
            chown = f"--chown={entry.pw_uid}:{entry.pw_gid} --numeric-ids"
        error = _fetch(gate, bid, point, f"home/{from_user}", home_items, home, chown)
        if error:
            problems.append({"what": "Some settings in your home folder didn't come back.", "details": error})
        error = _fetch(gate, bid, point, "system", system_items, root, "")
        if error:
            problems.append({"what": "Some System tweaks didn't come back.", "details": error})
    finally:
        keeper.stop()
        gate.call("lock", bid, hold)
    problems += _units(request.get("units", []))
    logger.info("migrate settings from %s: %d home, %d system, %d problems",
                point, len(home_items), len(system_items), len(problems))
    return {"home": len(home_items), "system": len(system_items), "problems": problems}


def _units(units: list) -> list[dict]:
    """The tweaks' own units, switched on (as they were on the old computer)."""
    problems = []
    if not units or os.environ.get("OMABACKUPS_SYSROOT"):
        return problems
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
    for unit in units if isinstance(units, list) else []:
        name = str(unit.get("name", "")) if isinstance(unit, dict) else ""
        if not name or "/" in name or not name.endswith((".service", ".timer", ".path", ".socket")):
            continue
        # A user unit: switched on for every user, as it was in /etc/systemd/user.
        command = ["systemctl", "--global", "enable", name] if unit.get("user") else \
            ["systemctl", "enable", "--now", name]
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode != 0:
            problems.append({"what": f"{name} couldn't be switched on.", "details": done.stderr.strip()})
    return problems
