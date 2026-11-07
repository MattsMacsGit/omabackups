"""`omabackups browse <point>` / `browse done` (D37: open a restore point in
your file manager, read-only) and `omabackups restore-files <point>` /
`restore-files stop` (Restore my files). Plus the two services' own runs."""

import argparse
import os
import shutil
import subprocess

from omabackups.core import rootjob
from omabackups.core.events import Events


def add(sub) -> None:
    b = sub.add_parser("browse", help="open a restore point in your file manager (read-only)")
    b.add_argument("point", help="the restore point, or done to close it")
    b.set_defaults(run=run_browse)
    r = sub.add_parser("restore-files", help="Restore my files: bring your home folder back")
    r.add_argument("point", help="the restore point, or stop")
    r.set_defaults(run=run_restore)
    serve = sub.add_parser("browse-serve", help=argparse.SUPPRESS)
    serve.add_argument("point")
    serve.add_argument("user")
    serve.set_defaults(run=_browse_serve)
    again = sub.add_parser("restore-run", help=argparse.SUPPRESS)
    again.add_argument("point")
    again.add_argument("user")
    again.set_defaults(run=_restore_run)


def open_folder(path: str) -> None:
    """In the user's default file manager (whatever they've set for folders),
    the way Omarchy starts apps: in their own session scope, detached."""
    command = ["xdg-open", path]
    if shutil.which("uwsm-app"):
        command = ["uwsm-app", "--", *command]
    subprocess.Popen(["setsid", *command], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def run_browse(args, events: Events) -> int:
    if args.point == "done":
        rootjob.run("browse-close", {})
        events.result({"closed": True}, "Closed. Your backup locks itself again.")
        return 0
    events.step("open", "Opening the restore point (read-only)...")
    answer = rootjob.run("browse-open", {"point": args.point})
    if not os.environ.get("OMABACKUPS_SYSROOT"):
        open_folder(answer["path"])
    events.result(answer, f"Open in your file manager: {answer['path']}\n"
                          "Copy anything you want back into your home folder. "
                          "When you're done: omabackups browse done")
    return 0


def run_restore(args, events: Events) -> int:
    if args.point == "stop":
        rootjob.run("restore-files-stop", {})
        events.result({"stopped": True}, "Stopped. Restore my files carries on where it left off next time.")
        return 0
    request = {"point": args.point}
    from omabackups.core import flow, state
    migrated = state.read(flow.MIGRATE) or {}
    if migrated.get("point") == args.point:     # after Migrate: its old user name, its picks
        request.update(from_user=migrated.get("from_user") or "", only=migrated.get("files") or None)
    answer = rootjob.run("restore-files-start", request)
    events.result(answer, "Bringing your files back. A file that's newer here is never "
                          "overwritten. The panel shows how it's going.")
    return 0


def _need_root() -> None:
    from omabackups.commands.plumbing import _need_root as need
    need()


def _browse_serve(args, events: Events) -> int:
    _need_root()
    from omabackups.restore import browse
    return browse.serve(args.point, args.user)


def _restore_run(args, events: Events) -> int:
    _need_root()
    from omabackups.restore import files
    return files.serve(args.point, args.user)
