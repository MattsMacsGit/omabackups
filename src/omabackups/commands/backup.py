"""`omabackups backup` (Back up now), `omabackups stop`, and the root side
`omabackups backup-run now|scheduled` that the backup service runs."""

import argparse
import os
import subprocess
import sys
import time

from omabackups.backup import check, health, progress, run, schedule
from omabackups.core import log, paths
from omabackups.core.errors import OmaError
from omabackups.core.events import Events

UNIT = "omabackups-backup@{}.service"
KINDS = ("now", "scheduled", "anyway", "forced")   # every backup service there is
# forced: Back up anyway after a partial restore (SPEC §9); never automatic.


def add(sub) -> None:
    now = sub.add_parser("backup", help="back up now")
    now.add_argument("--force-after-restore", action="store_true",
                     help="back up anyway while folders of a rescue or Migrate are still on the backup "
                          "(keeps only what's here; that restore point stays kept)")
    now.set_defaults(run=run_now)
    sub.add_parser("stop", help="stop the backup that's running").set_defaults(run=run_stop)
    away = sub.add_parser("away", help="answer the away-from-home question")
    answer = away.add_subparsers(dest="verb", metavar="answer", required=True)
    choice = answer.add_parser("answer", help="now: back up anyway; wait: until you're home")
    choice.add_argument("choice", choices=("now", "wait"))
    choice.set_defaults(run=run_away)
    sub.add_parser("health-run", help=argparse.SUPPRESS).set_defaults(run=run_health)
    root = sub.add_parser("backup-run", help=argparse.SUPPRESS)
    root.add_argument("kind", choices=KINDS)
    root.set_defaults(run=run_root)


# --- the user's side ---------------------------------------------------------

def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--no-ask-password", *args], capture_output=True, text=True)


def run_away(args, events: Events) -> int:
    if args.choice == "now":
        return _start_and_follow("anyway", events)
    events.result({"waiting": True}, "OK: it waits, and backs up once you're on a known network.")
    return 0


def run_now(args, events: Events) -> int:
    from omabackups.core import partial
    left = partial.waiting()
    if left and not getattr(args, "force_after_restore", False):
        raise partial.refusal(left)          # said here, before any service starts
    return _start_and_follow("forced" if left else "now", events)


def start(kind: str) -> float:
    """Start a backup (the service), without waiting for it. Returns when."""
    if not paths.server_file().exists():
        raise OmaError("No backup location is set up on this computer yet.",
                       "Set up backups first: omabackups setup server", code="not-set-up")
    started = time.time()
    if os.environ.get("OMABACKUPS_SYSROOT"):   # tests: no systemd here
        subprocess.run([sys.executable, "-m", "omabackups", "backup-run", kind], capture_output=True)
    else:
        done = _systemctl("start", "--no-block", UNIT.format(kind))
        if done.returncode != 0:
            raise OmaError("OmaBackups isn't allowed to start a backup on this computer.",
                           "Set up backups again, or refresh the link (see the guide).",
                           done.stderr.strip(), code="not-linked")
    return started


def _start_and_follow(kind: str, events: Events) -> int:
    started = start(kind)
    shown, said = "", 0.0
    while True:
        state = progress.read()
        if state.get("running") and state.get("started", 0) >= started - 5:
            heading = progress.text({k: state.get(k) for k in ("step", "part", "part_no", "parts")
                                     if state.get(k) is not None})
            if heading != shown:
                events.step(state.get("step", ""), heading)
                shown = heading
            # D49: the honest numbers; a line a minute in a terminal, every change for the panel.
            if state.get("total") and (events.as_json or time.monotonic() - said >= 60):
                if events.as_json:
                    events.progress(state.get("percent", 0), progress.text(state), state.get("left"))
                else:
                    events.message(progress.text(state))
                said = time.monotonic()
        busy = (not os.environ.get("OMABACKUPS_SYSROOT")
                and _systemctl("is-active", UNIT.format(kind)).stdout.strip() in ("active", "activating"))
        if not busy and not state.get("running"):
            break
        time.sleep(1)
    state = progress.read()
    if not state.get("ok"):
        error = state.get("error") or {}
        raise OmaError(error.get("what", "The backup didn't finish."), error.get("todo", ""),
                       error.get("details", ""), code=error.get("code", "backup-failed"))
    from omabackups.core import config
    config.automatic(True, "a Back up now finished (D29)")
    events.result({"point": state["point"], "how": state.get("how", {})},
                  f"Backed up: restore point {state['point']}.")
    return 0


def run_stop(args, events: Events) -> int:
    # One unit per call: some systemd versions refuse a multi-unit stop from a user (1.x lesson).
    # Every kind: "anyway" (the away question's Back up now) was left out once,
    # and Stop did nothing to it.
    for kind in KINDS:
        _systemctl("stop", UNIT.format(kind))
    events.result({"stopped": True}, "Stopped. Resume backup (omabackups backup) carries on from where it got to.")
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
            from omabackups.core import partial
            if left := partial.waiting():
                # Never on its own: it would push the gap over the backup (SPEC §9, audit 1.2).
                logger.info("automatic backup skipped: this system isn't whole yet "
                            "(restored from %s; still on the backup: %s)", left["point"], ", ".join(left["folders"]))
                return 0
            if run.load_record().get("automatic_paused"):
                logger.info("automatic backup skipped: waiting for a Back up now (D29)")
                return 0
            settings = schedule.user_settings(run.linked_user())
            go, why = schedule.due(settings, run.load_record().get("last_finished"))
            if not go:
                logger.info("automatic backup skipped: %s", why)
                return 0
        try:
            result = run.backup(progress.reporter(args.kind), anyway=args.kind == "anyway",
                                manual=args.kind != "scheduled", force_after_restore=args.kind == "forced")
        except check.AwayWait as exc:
            # Not a failure: it waits for your answer, or for a known network (D17).
            progress.write({"running": False, "ok": False, "waiting": "away", "size": exc.size,
                            "limit_mb": exc.limit_mb, "kind": args.kind, "error": exc.as_dict(),
                            "since": int(time.time())})
            if args.kind == "scheduled":
                logger.info("automatic backup waits: %s", exc.what)
                return 0
            raise
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


def run_health(args, events: Events) -> int:
    """The health timer's hourly tick (as root): start tonight's slice when due."""
    if os.geteuid() != 0 and not os.environ.get("OMABACKUPS_SYSROOT"):
        raise OmaError("This part of OmaBackups only runs as its health service.", code="not-root")
    if not paths.server_file().exists():
        return 0
    from omabackups.core import partial
    if partial.waiting():          # waits until the folders are back (audit 1.12)
        log.get("health").info("health check skipped: this system isn't whole yet")
        return 0
    settings = schedule.user_settings(run.linked_user())
    if not health.due(settings, health.load().get("started")):
        return 0
    import json

    from omabackups.root import keys
    from omabackups.where import location
    server = json.loads(paths.server_file().read_text())
    gate, _away = location.connect(server)
    gate.check_version()
    if gate.call("version").get("gate", 0) < 4:
        log.get("health").info("the server's gatekeeper is too old for the health check")
        return 0
    verdict = health.start_tonight(gate, server["backup"], settings["health.minutes"],
                                   keys.read_unlock_key(), wait=server.get("kind") == "disk")
    events.result(verdict, f"Tonight's health check started ({settings['health.minutes']} minutes).")
    return 0
