"""Commands the package's units and pkexec run as root. Not for typing:
they're hidden from --help.

  omabackups link            (pkexec, during setup: D27)
  omabackups root-job NAME   (omabackups-root@NAME.service: 5.2)
  omabackups desktop-rules install|remove   (udiskie leaves our disks alone: audit 7.4)
  omabackups refresh-rule    (the package's post-upgrade step: D57)
"""

import argparse

from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    link = sub.add_parser("link", help=argparse.SUPPRESS)
    link.set_defaults(run=_link)
    job = sub.add_parser("root-job", help=argparse.SUPPRESS)
    job.add_argument("job")
    job.set_defaults(run=_root_job)
    rules = sub.add_parser("desktop-rules", help=argparse.SUPPRESS)
    rules.add_argument("verb", choices=("install", "remove"))
    rules.set_defaults(run=_desktop_rules)
    sub.add_parser("refresh-rule", help=argparse.SUPPRESS).set_defaults(run=_refresh_rule)


def _refresh_rule(args, events: Events) -> int:
    _need_root()
    from omabackups.root import link
    done = link.refresh_rule()
    events.result({"refreshed": done}, "OmaBackups' permission rule is up to date." if done
                  else "Nothing linked here yet: setup writes the rule.")
    return 0


def _desktop_rules(args, events: Events) -> int:
    from omabackups.setup import udiskie
    if args.verb == "remove":
        udiskie.remove()
        events.result({"removed": True}, "udiskie opens every disk on its own again.")
        return 0
    note = udiskie.install()
    events.result({"note": note}, note or "udiskie leaves OmaBackups' disks alone when they're plugged in.")
    return 0


def _need_root() -> None:
    import os
    if os.geteuid() != 0 and not os.environ.get("OMABACKUPS_SYSROOT"):
        raise OmaError("This part of OmaBackups only runs as its root helper.",
                       "Use the panel or the other omabackups commands instead.", code="not-root")


def _link(args, events: Events) -> int:
    _need_root()
    from omabackups.root import link
    return link.run(args, events)


def _root_job(args, events: Events) -> int:
    _need_root()
    from omabackups.root import jobs
    return jobs.run(args, events)
