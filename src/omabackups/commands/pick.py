"""`omabackups pick`: Choose what gets backed up (the picker, in this terminal)."""

import getpass
import os

from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    sub.add_parser("pick", help="choose what gets backed up (opens the picker)").set_defaults(run=run)


def run(args, events: Events) -> int:
    if not (os.isatty(0) and os.isatty(1)):       # a terminal on both ends
        raise OmaError("The picker needs a terminal window.",
                       "Run omabackups pick in a terminal (the panel opens one for it).",
                       code="no-terminal")
    from omabackups.tui import picker
    saved = picker.run(getpass.getuser())
    events.result({"saved": saved},
                  "Saved. The next backup follows your choices: anything newly skipped leaves\n"
                  "the backup's working copy (older restore points keep it), anything newly\n"
                  "ticked is backed up." if saved else "Nothing was changed.")
    return 0
