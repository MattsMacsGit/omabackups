"""`omabackups rescue-usb later`: the Rescue USB's Later button (D11).
(Make / Refresh Rescue USB come with stage 9.)"""

from omabackups.core import state
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    p = sub.add_parser("rescue-usb", help="the Rescue USB")
    verbs = p.add_subparsers(dest="verb", metavar="later|preview|settings|wizard|make|refresh", required=True)
    verbs.add_parser("later", help="not now (the panel keeps reminding)").set_defaults(run=run_later)
    verbs.add_parser("preview", help="see the Rescue USB's screens (sample answers, nothing changes)") \
        .set_defaults(run=run_preview)
    p_set = verbs.add_parser("settings", help="write a new Rescue USB's settings to a folder (testing; "
                                              "takes the last stick's key off the server)")
    p_set.add_argument("folder")
    p_set.set_defaults(run=run_settings)
    verbs.add_parser("wizard", help="the rescue itself (runs on the Rescue USB)").set_defaults(run=run_wizard)
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


def run_preview(args, events: Events) -> int:
    """D47: every Rescue USB screen with sample answers, to agree them."""
    import os
    if not (os.isatty(0) and os.isatty(2)):
        raise OmaError("The preview needs a terminal window.", "Run it in a terminal, full screen.",
                       code="no-terminal")
    from omabackups.rescue import preview
    preview.run()
    events.result({"preview": True}, "Preview finished. Nothing was changed.")
    return 0


def run_settings(args, events: Events) -> int:
    from pathlib import Path
    from omabackups.core import rootjob
    from omabackups.rescue import settings
    bundle = rootjob.run("rescue-key", {})["settings"]
    folder = Path(args.folder).expanduser().resolve()
    settings.write(bundle, folder)
    events.result({"folder": str(folder)}, f"A Rescue USB's settings are in {folder}. "
                  "The last stick's key no longer opens anything.")
    return 0


def run_wizard(args, events: Events) -> int:
    """The wizard owns the whole screen: its results go to the log, not onto
    the screen under it (a stray "The rescue is done." sat beside the end screen)."""
    import io
    from omabackups.core import log
    from omabackups.rescue import wizard
    quiet = Events(as_json=True, out=io.StringIO())
    code = wizard.run(quiet)
    log.get("rescue").info("wizard finished: %s", quiet.out.getvalue().strip()[-500:])
    return code
