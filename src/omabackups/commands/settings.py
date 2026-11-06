"""`omabackups settings get [name]` / `omabackups settings set <name> <value>`."""

from omabackups.core import config, log
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    p = sub.add_parser("settings", help="see or change settings")
    verbs = p.add_subparsers(dest="verb", metavar="get|set", required=True)
    get = verbs.add_parser("get", help="show settings")
    get.add_argument("name", nargs="?", help="one setting (default: all)")
    get.set_defaults(run=run_get)
    put = verbs.add_parser("set", help="change one setting")
    put.add_argument("name")
    put.add_argument("value")
    put.set_defaults(run=run_set)


def _show(value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def run_get(args, events: Events) -> int:
    values = config.load()
    if args.name:
        if args.name not in values:
            raise OmaError(f"There is no setting called '{args.name}'.",
                           f"The settings are: {', '.join(config.names())}.",
                           code="bad-setting")
        values = {args.name: values[args.name]}
    text = "\n".join(f"{name} = {_show(value)}" for name, value in values.items())
    events.result({"settings": values}, text)
    return 0


def run_set(args, events: Events) -> int:
    value = config.parse_value(args.name, args.value)
    values = config.load()
    values[args.name] = value
    config.save(values)
    log.get("settings").info("set %s = %r", args.name, value)
    events.result({"settings": {args.name: value}}, f"{args.name} = {_show(value)}")
    return 0
