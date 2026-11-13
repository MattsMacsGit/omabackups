"""Which step of the flow (BUILD 6.1) this computer is at: one function, one
answer (D10). The panel shows only what can be used at that step.

Each step is decided from state files that later parts write only after
their step succeeded. Stage 1 writes none of them, so a new install is
always at NOT_SET_UP.
"""

from enum import Enum

from omabackups.core import state


class Step(str, Enum):
    NOT_SET_UP = "not-set-up"            # B: Set up backups / Migrate from another system
    SETTING_UP = "setting-up"            # C: the backup location is chosen, first backup not done
    MIGRATING = "migrating"              # F: Migrate started, not finished
    RESTORE_FILES = "restore-files"      # D line: "Restore my files to finish"
    EVERYDAY = "everyday"                # D: the everyday panel


# The state file that records each finished milestone (written by later stages).
SETUP = "setup"          # {"where": "server"|"disk", "first_backup": bool}
MIGRATE = "migrate"      # {"done": bool, "files_restored": bool}


def where() -> Step:
    migrate = state.read(MIGRATE)
    if migrate is not None:
        if not migrate.get("done"):
            return Step.MIGRATING
        # D52: after a Quick Rescue the folders come back as often as you like,
        # until a backup ends it (and takes the panel to its everyday page).
        if migrate.get("rescued") and migrate.get("files"):
            if not _a_backup_since(migrate.get("at", 0)):
                return Step.RESTORE_FILES
        elif not migrate.get("files_restored"):
            return Step.RESTORE_FILES

    if migrate is None and _joined():
        return Step.MIGRATING            # joined a backup; Migrate not finished yet

    setup = state.read(SETUP)
    if setup is None:
        # After a finished Migrate, the first backup (and handover) is next;
        # once it has run, this computer owns the backup: everyday.
        if migrate is None:
            return Step.NOT_SET_UP
        return Step.EVERYDAY if _a_backup_finished() else Step.SETTING_UP
    if not setup.get("first_backup") and not _a_backup_finished():
        return Step.SETTING_UP
    return Step.EVERYDAY


def _joined() -> bool:
    """The root side's server file says this computer joined a backup to migrate."""
    import json
    from omabackups.core import paths
    try:
        return bool(json.loads(paths.server_file().read_text()).get("migrating"))
    except (OSError, ValueError):
        return False


def _a_backup_since(when: int) -> bool:
    """A backup finished after `when` (the rescue's own record keeps the old time)."""
    import json
    from omabackups.core import paths
    try:
        record = json.loads((paths.system_state_dir() / "backup.json").read_text())
    except (OSError, ValueError):
        return False
    return int(record.get("last_finished") or 0) > int(when or 0)


def _a_backup_finished() -> bool:
    """The root side's record (readable by everyone) says a backup finished."""
    import json
    from omabackups.core import paths
    try:
        return bool(json.loads((paths.system_state_dir() / "backup.json").read_text()).get("last_point"))
    except (OSError, ValueError):
        return False
