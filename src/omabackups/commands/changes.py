"""`omabackups changes`: Your changes to Omarchy (D9, read only).

How this system differs from a fresh Omarchy, as noted by the latest backup.
Under the title: "Latest backup was Tuesday 12:33 pm" (never "from <restore
point>": that reads like "changed since", BUILD 3.2).
"""

import json
from datetime import datetime

from omabackups.audit import model
from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    sub.add_parser("changes", help="your changes to Omarchy, as of the latest backup").set_defaults(run=run)


def when(stamp: int) -> str:
    moment = datetime.fromtimestamp(stamp)
    hour = moment.strftime("%I:%M %p").lstrip("0").lower()
    return f"{moment:%A} {hour}"


def run(args, events: Events) -> int:
    try:
        audit = json.loads((paths.system_state_dir() / "changes.json").read_text())
    except (OSError, ValueError):
        raise OmaError("There's no list of your changes to Omarchy yet.",
                       "It's made with every backup: back up once, then look again.",
                       code="no-changes") from None
    title = f"Your changes to Omarchy\nLatest backup was {when(audit['made'])}\n"
    events.result(audit, title + "\n" + model.summary(audit))
    return 0
