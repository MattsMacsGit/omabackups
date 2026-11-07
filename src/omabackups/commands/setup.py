"""`omabackups setup server`: set up backups to a backup server (6.1 C).

Asks in the terminal for anything not given. Passwords are never taken on
the command line (anyone on the computer could read them there).
"""

import json
import os


from omabackups.core import flow, paths
from omabackups.core.errors import OmaError
from omabackups.core.events import Events
from omabackups.backup.check import human
from omabackups.setup import menu, places, server

PASSWORD_TITLE = "Choose your backup's password"
PASSWORD_NOTE = ("Everyday backups don't need it: this computer has its own key.\n"
                 "You need it for a Rescue USB or a new computer. Write it down:\n"
                 "without it, nobody can open your backup, not even you.")


def add(sub) -> None:
    p = sub.add_parser("setup", help="set up where your backups go")
    kinds = p.add_subparsers(dest="kind", metavar="server|disk", required=True)
    s = kinds.add_parser("server", help="a backup server on the network")
    s.add_argument("address", nargs="?", help="the server's address on your network")
    s.add_argument("--login", help="your user name on the server")
    s.add_argument("--folder", help="the folder on the server that holds the backup store")
    s.add_argument("--size", type=int, help="your backup's size, in GB")
    s.add_argument("--update", action="store_true",
                   help="update OmaBackups on the server you already back up to")
    s.set_defaults(run=run_server)
    d = kinds.add_parser("disk", help="a backup disk plugged into this computer (it gets erased)")
    d.add_argument("disk", nargs="?", help="the disk, e.g. /dev/sdb (asked if not given)")
    d.set_defaults(run=run_disk)
    sub.add_parser("start-over", help="forget this computer's backup location (the backup "
                   "itself is kept)").set_defaults(run=run_start_over)


def cipher_name(cipher: str) -> str:
    if "adiantum" in cipher:
        return "Adiantum, the fast choice for a server without AES"
    if cipher.startswith("aes-xts"):
        return "AES"
    return cipher


def run_update(args, events: Events) -> int:
    """Update the gatekeeper on the server this computer already uses (keeps the backup)."""
    try:
        address = json.loads(paths.server_file().read_text())["address"]
    except (OSError, ValueError, KeyError):
        raise OmaError("This computer doesn't back up to a server yet.",
                       "Set one up first: omabackups setup server", code="not-set-up") from None
    events.message("Update OmaBackups on your backup server. Your backup and its restore points\n"
                   "are kept. This asks for your login on the server and its sudo password.")
    login = args.login or menu.ask("Your user name on the server", os.environ.get("USER", ""))
    session = server.Login(address, login)
    events.message("\nLogging in to your backup server (its password, for your login there)...")
    try:
        installed = server.install(session, "-", server.public_key())
    finally:
        session.close()
    events.result({"gate": installed.get("gate")},
                  f"OmaBackups on your backup server is up to date (gatekeeper version {installed.get('gate')}).")
    return 0


def _size(place) -> int:
    """How big the backup in a disk's free space is, in GB (D30)."""
    offered = places.sizes(place.free)
    if not offered:
        raise OmaError(f"{place.name} has only {human(place.free)} free: not enough for a backup.",
                       "Pick another disk, or make room on this one, then run setup again.",
                       code="no-room")
    options = [f"{n} GB" for n in offered] + ["Another size"]
    picked = menu.choose(f"How big should your backup be? ({human(place.free)} free; "
                         "it can grow later)", options, selected=min(1, len(offered) - 1))
    if picked < len(offered):
        return offered[picked]
    typed = menu.ask("Size in GB", str(offered[-1]))
    if not typed.isdigit() or not 1 <= int(typed) <= place.free >> 30:
        raise OmaError(f"The size must be a number of GB, at most {place.free >> 30}.",
                       "Run setup again and pick or type a size.", code="cancelled")
    return int(typed)


def _where_on_server(args, events: Events, session) -> tuple[str, int, bool]:
    """6.1 C step 2 (D30): pick a disk, then the whole disk or its free space."""
    menu.say("\nLogging in to your backup server (its password, for your login there)...")
    if args.folder:
        return server.check_store(args.folder), args.size or 100, False
    found = session.places()
    if not found:
        raise OmaError("Your backup server has no disks that OmaBackups can see.",
                       "Check the server's disks are plugged in, then run setup again.",
                       code="no-disk")
    while True:
        menu.title("Where on the server should your backup go?",
                   "Pick a disk. Next you choose: the whole disk, or its free space.")
        place = found[menu.choose("Disks on your backup server", [p.line() for p in found])]
        way = _way(place)
        if way:
            break
    if way == "whole":
        return f"disk:{place.path}:{place.size}", 0, True
    size = args.size or _size(place)
    menu.say(f"\nYour backup goes in {place.folder} on the server ({size} GB).")
    return place.folder, size, False


def _way(place) -> str:
    """The whole disk or its free space: "whole", "space", or "" to pick again."""
    menu.title(place.name, "\n".join(f"  {w}" for w in place.contents) or "  Empty.")
    ways = []
    if place.mount:
        ways.append(("space", f"Its free space  ·  {human(place.free)}  ·  nothing is erased"))
    if not place.system:
        ways.append(("whole", f"The whole disk  ·  {human(place.size)}  ·  everything on it is erased"))
    ways.append(("", "Pick another disk"))
    return ways[menu.choose("How should your backup use it?", [w[1] for w in ways])][0]


def run_server(args, events: Events) -> int:
    if args.update:
        return run_update(args, events)
    if flow.where() is not flow.Step.NOT_SET_UP:
        raise OmaError("OmaBackups is already set up on this computer.",
                       "To update OmaBackups on the server: omabackups setup server --update. "
                       "To use a different backup location, Start over from Settings first.",
                       code="already-set-up")
    menu.title("Set up backups to a backup server",
               "Three passwords, each asked once: this computer's, your login on the\n"
               "server, and the server's sudo password. Then your backup's own password.")
    address = args.address or menu.ask("The server's address", placeholder="for example 192.168.1.20")
    login = args.login or menu.ask("Your user name on the server", os.environ.get("USER", ""))
    if not address or not login:
        raise OmaError("The server's address and your user name on it are both needed.",
                       code="cancelled")

    events.step("link", "Linking this computer to OmaBackups (this computer's password)...")
    pub = server.link()
    login_session = server.Login(address, login)
    try:
        store, size, disk = _where_on_server(args, events, login_session)
        installed = server.install(login_session, store, pub)
    finally:
        login_session.close()
    for warning in installed.get("warnings", []):
        events.message(f"Note about the server: {warning}")
    if disk:   # a disk of its own: the backup takes (almost) all of it
        size = max(1, int(installed.get("store_free", 0) * 0.97) >> 30)

    menu.title(PASSWORD_TITLE, PASSWORD_NOTE)
    password = _password()
    events.step("create", "Creating your backup on the server (this takes a minute)...")
    made = server.create(address, login_session.host_keys(), size << 30, password)
    events.result({"backup": made["backup"], "cipher": made["cipher"], "size": made["size"]},
                  f"\nYour backup is set up on the server ({size} GB, encrypted with "
                  f"{cipher_name(made['cipher'])}).\n"
                  "Next: the first backup.")
    return 0


def run_disk(args, events: Events) -> int:
    """6.1 C, a backup disk: pick it (every disk listed, its contents warned),
    choose your backup's password, then it's erased and set up."""
    from omabackups.core import rootjob, state
    from omabackups.setup import disks
    if flow.where() is not flow.Step.NOT_SET_UP:
        raise OmaError("OmaBackups is already set up on this computer.",
                       "To use a different backup location, Start over first: "
                       "omabackups start-over", code="already-set-up")
    found = disks.disks()
    if not found:
        raise OmaError("There's no disk to pick (only the one this system runs from).",
                       "Plug in the backup disk, then try again.", code="no-disk")
    if args.disk:
        chosen = next((d for d in found if d.path == args.disk), None)
        if chosen is None:
            raise OmaError(f"{args.disk} isn't one of the disks you can pick.",
                           "Run omabackups setup disk to see the list.", code="no-disk")
    else:
        while True:
            menu.title("Set up backups to a backup disk",
                       "Pick the disk. The one you pick is erased and used only for backups.")
            chosen = found[menu.choose("Disks plugged in here", [d.line() for d in found])]
            menu.title(chosen.line(), "\n".join(f"  {w}" for w in chosen.warnings))
            if menu.choose("Use this disk?", ["Use it: erase it and back up to it",
                                              "Pick another disk"]) == 0:
                break
    events.step("link", "Linking this computer to OmaBackups (this computer's password)...")
    server.link()
    menu.title(PASSWORD_TITLE, PASSWORD_NOTE)
    password = _password()
    events.step("create", "Erasing the disk and creating your backup on it...")
    made = rootjob.run("create-disk", {"device": chosen.path, "size": chosen.size,
                                       "model": chosen.model, "password": password})
    state.write(flow.SETUP, {"where": "disk", "first_backup": False})
    events.result(made, f"\nYour backup is set up on {chosen.line()}, encrypted with "
                        f"{cipher_name(made['cipher'])}.\nNext: the first backup.")
    return 0


def run_start_over(args, events: Events) -> int:
    """D28: this computer forgets its backup location; nothing in the backup is deleted."""
    from omabackups.core import rootjob, state
    if flow.where() is flow.Step.NOT_SET_UP and not paths.server_file().exists():
        events.result({"forgot": None}, "OmaBackups isn't set up on this computer: nothing to forget.")
        return 0
    answer = rootjob.run("start-over", {})
    state.remove(flow.SETUP)
    where = {"disk": "on the backup disk", "server": "on your backup server"}.get(answer["forgot"], "")
    events.result(answer, "This computer has forgotten its backup location.\n"
                          f"Your backup is still there {where}, with all its restore points.\n"
                          "Next: Set up backups (omabackups setup server, or setup disk).")
    return 0
