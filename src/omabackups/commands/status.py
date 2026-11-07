"""`omabackups status`: where OmaBackups is up to, in words (or everything
the panel shows, with --json: status_data.py builds it)."""

from datetime import datetime

from omabackups.commands import status_data
from omabackups.core import flow
from omabackups.core.events import Events

_TEXT = {
    flow.Step.NOT_SET_UP: (
        "OmaBackups is not set up on this computer yet.\n"
        "Open the OmaBackups panel and choose Set up backups, "
        "or Migrate from another system."
    ),
    flow.Step.SETTING_UP: "OmaBackups is being set up: the first backup hasn't run yet.",
    flow.Step.MIGRATING: "Migrate from another system has started and isn't finished yet.",
    flow.Step.RESTORE_FILES: "Restore my files to finish. Automatic backups wait until then.",
    flow.Step.EVERYDAY: "OmaBackups is set up and backing up.",
}


def add(sub) -> None:
    p = sub.add_parser("status", help="where OmaBackups is up to on this computer")
    p.set_defaults(run=run)


def run(args, events: Events) -> int:
    data = status_data.build()
    text = _TEXT[flow.Step(data["flow"])]
    h = data["header"] or {}
    if h.get("last_point"):
        when = datetime.fromtimestamp(h["last_finished"]).strftime("%A %-I:%M %p")
        text += f"\nLast backup: {when} (restore point {h['last_point']}), to {h['where']}."
    for item in data["lines"]:
        text += f"\n{item['title']}" + (f": {item['text']}" if item["text"] else "")
    if data["running"]:
        from omabackups.backup import progress
        text += f"\nRunning now: {progress.text(data['running'])}"
    events.result(data, text)
    return 0
