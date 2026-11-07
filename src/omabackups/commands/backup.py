"""`omabackups backup` (Back up now), `omabackups stop`, and the root side
`omabackups backup-run now|scheduled` that the backup service runs."""

import argparse
import os
import subprocess
import sys
import time

from omabackups.backup import progress, run, schedule
from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.events import Events

UNIT = "omabackups-backup@{}.service"


def add(sub) -> None:
    sub.add_parser("backup", help="back up now").set_defaults(run=run_now)
    sub.add_parser("stop", help="stop the backup that's running").set_defaults(run=run_stop)
    root = sub.add_parser("backup-run", help=argparse.SUPPRESS)
    root.add_argument("kind", choices=("now", "scheduled"))
    root.set_defaults(run=run_root)


# --- the user's side ---------------------------------------------------------

def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--no-ask-password", *args], capture_output=True, text=True)


def run_now(args, events: Events) -> int:
    if not paths.server_file().exists():
        raise OmaError("No backup location is set up on this computer yet.",
                       "Set up backups first: omabackups setup server", code="not-set-up")
    started = time.time()
    if os.environ.get("OMABACKUPS_SYSROOT"):   # tests: no systemd here
        subprocess.run([sys.executable, "-m", "omabackups", "backup-run", "now"], capture_output=True)
    else:
        done = _systemctl("start", "--no-block", UNIT.format("now"))
        if done.returncode != 0:
            raise OmaError("OmaBackups isn't allowed to start a backup on this computer.",
                           "Set up backups again, or refresh the link (see the guide).",
                           done.stderr.strip(), code="not-linked")
    shown = ""
    while True:
        state = progress.read()
        if state.get("running") and state.get("started", 0) >= started - 5:
            line = progress.text(state)
            if line != shown:
                events.step(state.get("step", ""), line)
                shown = line
        busy = (not os.environ.get("OMABACKUPS_SYSROOT")
                and _systemctl("is-active", UNIT.format("now")).stdout.strip() in ("active", "activating"))
        if not busy and not state.get("running"):
            break
        time.sleep(1)
    state = progress.read()
    if not state.get("ok"):
        error = state.get("error") or {}
        raise OmaError(error.get("what", "The backup didn't finish."), error.get("todo", ""),
                       error.get("details", ""), code=error.get("code", "backup-failed"))
    events.result({"point": state["point"], "how": state.get("how", {})},
                  f"Backed up: restore point {state['point']}.")
    return 0


def run_stop(args, events: Events) -> int:
    # One unit per call: some systemd versions refuse a multi-unit stop from a user (1.x lesson).
    for kind in ("now", "scheduled"):
        _systemctl("stop", UNIT.format(kind))
    events.result({"stopped": True}, "Stopped. The next backup picks up where this one stopped.")
    return 0


# --- the root side (the service) ---------------------------------------------

def run_root(args, events: Events) -> int:
    if os.geteuid() != 0 and not os.environ.get("OMABACKUPS_SYSROOT"):
        raise OmaError("This part of OmaBackups only runs as its backup service.",
                       "Use: omabackups backup", code="not-root")
    logger = log.get("backup")
    with progress.only_one() as mine:
        if not mine:
            if args.kind == "scheduled":
                return 0
            raise OmaError("A backup is already running.", "Wait for it to finish.", code="busy")
        if args.kind == "scheduled":
            if not paths.server_file().exists():
                return 0
            settings = schedule.user_settings(run.linked_user())
            go, why = schedule.due(settings, run.load_record().get("last_finished"))
            if not go:
                logger.info("automatic backup skipped: %s", why)
                return 0
        try:
            result = run.backup(progress.reporter(args.kind))
        except OmaError as exc:
            progress.write({"running": False, "ok": False, "error": exc.as_dict(), "kind": args.kind})
            raise
        except BaseException as exc:
            progress.write({"running": False, "ok": False, "kind": args.kind,
                            "error": {"what": "The backup stopped.", "todo": "The next backup "
                                      "picks up where this one stopped.", "details": repr(exc)}})
            raise
        progress.write({"running": False, "ok": True, "kind": args.kind, "finished": int(time.time()),
                        **result})
    events.result(result, f"Backed up: restore point {result['point']}.")
    return 0
