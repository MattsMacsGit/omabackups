"""`omabackups points` (the restore points), `keep <point>`, `release <point>`,
and `password change` (your backup's password)."""

import getpass
from datetime import datetime

from omabackups.commands import status_data
from omabackups.core import rootjob
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    sub.add_parser("points", help="your restore points").set_defaults(run=run_points)
    for verb, about in (("keep", "keep a restore point (never thinned or deleted)"),
                        ("release", "stop keeping a restore point")):
        p = sub.add_parser(verb, help=about)
        p.add_argument("point")
        p.set_defaults(run=run_keep, keep=verb == "keep")
    pw = sub.add_parser("password", help="your backup's password")
    pw.add_subparsers(dest="verb", metavar="change", required=True).add_parser(
        "change", help="change your backup's password").set_defaults(run=run_password)


def run_points(args, events: Events) -> int:
    pts = status_data.points(status_data._read(status_data.paths.system_state_dir() / "backup.json"))
    lines = [f"{p['name']}  {datetime.fromtimestamp(p['when']):%a %-d %b %Y %-I:%M %p}"
             + ("  (kept)" if p["kept"] else "") for p in pts if p["when"]]
    events.result({"points": pts}, "\n".join(lines) or "No restore points yet.")
    return 0


def run_keep(args, events: Events) -> int:
    answer = rootjob.run("keep", {"point": args.point, "keep": args.keep})
    events.result(answer, f"{args.point} is {'kept' if args.keep else 'no longer kept'}.")
    return 0


def run_password(args, events: Events) -> int:
    old = getpass.getpass("Your backup's current password: ")
    while True:
        new = getpass.getpass("The new password: ")
        if len(new) < 8:
            events.message("Use at least 8 characters.")
            continue
        if getpass.getpass("Type it again: ") == new:
            break
        events.message("Those two didn't match. Try again.")
    rootjob.run("change-password", {"old": old, "new": new})
    events.result({"changed": True}, "Your backup's password is changed. Write the new one down: "
                  "you need it for the Rescue USB and for Migrate.")
    return 0
