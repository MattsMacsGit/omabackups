"""The omabackups command: the frame every command runs inside.

stdout carries answers only (plain sentences, or JSON lines with --json).
Logs and errors go to stderr and the log file (BUILD 8.2).
Every error the user can hit comes out as what happened + what to do +
details to copy; exit code 1 for those, 2 for a mistyped command.
"""

import argparse
import sys

from omabackups import __version__
from omabackups.commands import backup, plumbing, settings, setup, status
from omabackups.core import log
from omabackups.core.errors import OmaError, unexpected
from omabackups.core.events import Events

COMMANDS = (status, backup, setup, settings, plumbing)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="omabackups",
        description="OmaBackups: backups, rescue and migration for Omarchy.",
    )
    p.add_argument("--json", action="store_true", help="answer in JSON lines (for the panel)")
    p.add_argument("-v", "--verbose", action="store_true", help="show the log as it happens")
    p.add_argument("--version", action="version", version=f"omabackups {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<command>", required=True)
    for command in COMMANDS:
        command.add(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    events = Events(as_json=args.json)
    logger = log.setup(verbose=args.verbose)
    logger.debug("omabackups %s: %s", __version__, args.command)
    try:
        return args.run(args, events)
    except OmaError as exc:
        logger.error("%s | %s", exc.what, exc.details)
        events.error(exc)
        return 1
    except KeyboardInterrupt:
        events.error(OmaError("Stopped.", code="stopped"))
        return 130
    except Exception as exc:  # noqa: BLE001 - every bug still gets a proper message
        error = unexpected(exc)
        logger.error("unexpected: %s", error.details)
        events.error(error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
