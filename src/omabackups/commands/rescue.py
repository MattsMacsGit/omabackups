"""`omabackups rescue-usb later`: the Rescue USB's Later button (D11).
(Make / Refresh Rescue USB come with stage 9.)"""

from omabackups.core import state
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    p = sub.add_parser("rescue-usb", help="the Rescue USB")
    verbs = p.add_subparsers(dest="verb", metavar="later|make|refresh", required=True)
    verbs.add_parser("later", help="not now (the panel keeps reminding)").set_defaults(run=run_later)
    for verb in ("make", "refresh"):
        verbs.add_parser(verb, help=f"{verb} the Rescue USB (comes in a later version)").set_defaults(run=run_soon)


def run_later(args, events: Events) -> int:
    mine = state.read("panel") or {}
    state.write("panel", {**mine, "rescue_later": True})
    events.result({"rescue_later": True}, "OK: the panel keeps a reminder until you make one.")
    return 0


def run_soon(args, events: Events) -> int:
    raise OmaError("Making a Rescue USB isn't built yet.", "It comes with a later version of OmaBackups.",
                   code="not-yet")
