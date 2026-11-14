"""`omabackups remove`: Remove OmaBackups (audit 10.2). A terminal, from the
panel's Settings too. Wording agreed 14 Nov (SPEC-2.0.md)."""

import shutil

from omabackups.core import paths, rootjob
from omabackups.core.errors import OmaError
from omabackups.core.events import Events


def add(sub) -> None:
    sub.add_parser("remove", help="remove OmaBackups from this computer (it asks first)").set_defaults(run=run_remove)


def run_remove(args, events: Events) -> int:
    from omabackups.setup import menu, udiskie
    menu.title("Remove OmaBackups from this computer?",
               "Its services, snapshots and settings go. Your backup stays, so you can install "
               "OmaBackups again and carry on.")
    if not menu.confirm("Remove OmaBackups?", yes="Remove", no="Cancel"):
        raise OmaError("Nothing was removed.", code="cancelled")
    delete = False
    if paths.server_file().exists():
        import json
        where = "backup disk" if json.loads(paths.server_file().read_text()).get("kind") == "disk" \
            else "backup server"
        menu.title(f"Delete your backup on your {where} too?",
                   "Every restore point in it goes, for good. This can't be undone.")
        delete = menu.confirm("Delete your backup?", yes="Delete it", no="Keep my backup") and \
            menu.confirm("Are you sure? Every restore point goes, for good.", yes="Delete it", no="Keep it")
    answer = rootjob.run("remove", {"delete_backup": delete})
    udiskie.remove()
    for folder in (paths.config_dir(), paths.state_dir()):
        shutil.rmtree(folder, ignore_errors=True)
    events.result(answer, ("OmaBackups is removed, and so is your backup." if answer.get("destroyed")
                           else "OmaBackups is removed. Your backup is kept.")
                  + "\nTo finish, remove the package: sudo pacman -R omabackups")
    return 0
