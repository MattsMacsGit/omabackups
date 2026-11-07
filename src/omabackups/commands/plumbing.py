"""Commands the package's units and pkexec run as root. Not for typing:
they're hidden from --help.

  omabackups link            (pkexec, during setup: D27)
  omabackups root-job NAME   (omabackups-root@NAME.service: 5.2)
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
