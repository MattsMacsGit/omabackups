"""`omabackups status`: everything the panel shows, in one answer."""

from omabackups import __version__
from omabackups.core import flow, ids
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
    flow.Step.EVERYDAY: "OmaBackups is set up.",
}


def add(sub) -> None:
    p = sub.add_parser("status", help="where OmaBackups is up to on this computer")
    p.set_defaults(run=run)


def run(args, events: Events) -> int:
    step = flow.where()
    system = ids.system_id()
    data = {
        "flow": step.value,
        "system": {"id": system, "short": ids.short(system)},
        "version": __version__,
        # Filled in by later stages: the panel header and the lines that
        # appear only when true (BUILD 6.1 D).
        "header": None,
        "lines": [],
    }
    events.result(data, _TEXT[step])
    return 0
