"""`omabackups setup server`: set up backups to a backup server (6.1 C).

Asks in the terminal for anything not given. Passwords are never taken on
the command line (anyone on the computer could read them there).
"""

import getpass
import os

from omabackups.core import flow
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
    kinds = p.add_subparsers(dest="kind", metavar="server", required=True)
    s = kinds.add_parser("server", help="a backup server on the network")
    s.add_argument("address", nargs="?", help="the server's address on your network")
    s.add_argument("--login", help="your user name on the server")
    s.add_argument("--folder", help="the folder on the server that holds the backup store")
    s.add_argument("--size", type=int, help="your backup's size, in GB")
    s.set_defaults(run=run_server)


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


def run_server(args, events: Events) -> int:
    if flow.where() is not flow.Step.NOT_SET_UP:
        raise OmaError("OmaBackups is already set up on this computer.",
                       "To use a different backup location, Start over from Settings first.",
                       code="already-set-up")
    events.message("Set up backups to a backup server.\n"
                   "This asks for three passwords, each once: this computer's, your login\n"
                   "on the server, and the server's sudo password. Then you choose your\n"
                   "backup's own password.")
    address = args.address or _ask("The server's address (for example 192.168.1.20)")
    login = args.login or _ask("Your user name on the server", os.environ.get("USER", ""))
    folder = server.check_store(args.folder or _ask(
        "The folder on the server for the backup store (on a disk with room)"))
    size = args.size or int(_ask("Your backup's size in GB (it can grow later)", "100"))
    if not address or not login:
        raise OmaError("The server's address and your user name on it are both needed.",
                       code="cancelled")

    events.step("link", "Linking this computer to OmaBackups (this computer's password)...")
    pub = server.link()
    login_session = server.Login(address, login)
    try:
        installed = server.install(login_session, folder, pub)
    finally:
        login_session.close()
    for warning in installed.get("warnings", []):
        events.message(f"Note about the server: {warning}")

    events.message(PASSWORD_EXPLAINER)
    password = _password()
    events.step("create", "Creating your backup on the server (this takes a minute)...")
    made = server.create(address, login_session.host_keys(), size << 30, password)
    events.result({"backup": made["backup"], "cipher": made["cipher"], "size": made["size"]},
                  f"\nYour backup is set up on the server ({size} GB, encrypted with "
                  f"{cipher_name(made['cipher'])}).\n"
                  "Next: the first backup.")
    return 0
