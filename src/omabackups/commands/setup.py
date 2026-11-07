"""`omabackups setup server`: set up backups to a backup server (6.1 C).

Asks in the terminal for anything not given. Passwords are never taken on
the command line (anyone on the computer could read them there).
"""

import getpass
import json
import os


from omabackups.core import flow, paths
from omabackups.core.errors import OmaError
from omabackups.core.events import Events
from omabackups.setup import server

PASSWORD_EXPLAINER = (
    "\nChoose your backup's password.\n"
    "Everyday backups don't need it: this computer has its own key. You need it to\n"
    "open your backup from a Rescue USB or from a new computer (Migrate). Write it\n"
    "down and keep it somewhere safe: without it, nobody can open your backup, not\n"
    "even you."
)


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


def _ask(text: str, default: str = "") -> str:
    shown = f"{text} [{default}]: " if default else f"{text}: "
    answer = input(shown).strip()
    return answer or default


def _password() -> str:
    while True:
        first = getpass.getpass("Your backup's password: ")
        if len(first) < 8:
            print_err("Use at least 8 characters.")
            continue
        if getpass.getpass("Type it again: ") == first:
            return first
        print_err("Those two didn't match. Try again.")


def print_err(text: str) -> None:
    import sys
    sys.stderr.write(text + "\n")


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
    login = args.login or _ask("Your user name on the server", os.environ.get("USER", ""))
    session = server.Login(address, login)
    events.message("\nLogging in to your backup server (its password, for your login there)...")
    try:
        installed = server.install(session, "-", server.public_key())
    finally:
        session.close()
    events.result({"gate": installed.get("gate")},
                  f"OmaBackups on your backup server is up to date (gatekeeper version {installed.get('gate')}).")
    return 0


def _where_on_server(args, events: Events, session) -> tuple[str, int, bool]:
    """6.1 C step 2: [a disk of its own] or [space on a disk it has, size ___]."""
    if args.folder:
        size = args.size or int(_ask("Your backup's size in GB (it can grow later)", "100"))
        events.message("\nLogging in to your backup server (its password, for your login there)...")
        return server.check_store(args.folder), size, False
    events.message("\nLogging in to your backup server (its password, for your login there)...")
    found = session.disks()
    events.message("\nWhere on the server should your backup go?\n")
    for n, d in enumerate(found, 1):
        events.message(f"  {n}. A disk of its own: {d.line()} (erased)\n"
                       + "".join(f"       {w}\n" for w in d.warnings))
    events.message(f"  {len(found) + 1}. A folder on a disk the server already has "
                   "(you choose the size; nothing is erased)\n")
    choice = _ask("Which (number)")
    if not choice.isdigit() or not 1 <= int(choice) <= len(found) + 1:
        raise OmaError("Nothing was picked, so nothing was changed.", code="cancelled")
    if int(choice) == len(found) + 1:
        folder = server.check_store(_ask("The folder on the server (on a disk with room)"))
        size = args.size or int(_ask("Your backup's size in GB (it can grow later)", "100"))
        return folder, size, False
    chosen = found[int(choice) - 1]
    events.message(f"\n{chosen.line()} on the server will be erased:\n"
                   + "".join(f"  - {w}\n" for w in chosen.warnings))
    return f"disk:{chosen.path}:{chosen.size}", 0, True


def run_server(args, events: Events) -> int:
    if args.update:
        return run_update(args, events)
    if flow.where() is not flow.Step.NOT_SET_UP:
        raise OmaError("OmaBackups is already set up on this computer.",
                       "To update OmaBackups on the server: omabackups setup server --update. "
                       "To use a different backup location, Start over from Settings first.",
                       code="already-set-up")
    events.message("Set up backups to a backup server.\n"
                   "This asks for three passwords, each once: this computer's, your login\n"
                   "on the server, and the server's sudo password. Then you choose your\n"
                   "backup's own password.")
    address = args.address or _ask("The server's address (for example 192.168.1.20)")
    login = args.login or _ask("Your user name on the server", os.environ.get("USER", ""))
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

    events.message(PASSWORD_EXPLAINER)
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
        events.message("Pick the backup disk. Read what's on each one: the disk you pick is erased.\n")
        for n, d in enumerate(found, 1):
            events.message(f"  {n}. {d.line()}\n" + "".join(f"       {w}\n" for w in d.warnings))
        choice = _ask("Which disk (number)")
        if not choice.isdigit() or not 1 <= int(choice) <= len(found):
            raise OmaError("Nothing was picked, so nothing was erased.", code="cancelled")
        chosen = found[int(choice) - 1]
    events.message(f"\n{chosen.line()} will be erased:\n"
                   + "".join(f"  - {w}\n" for w in chosen.warnings))
    events.step("link", "Linking this computer to OmaBackups (this computer's password)...")
    server.link()
    events.message(PASSWORD_EXPLAINER)
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
