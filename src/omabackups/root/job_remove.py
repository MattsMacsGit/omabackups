"""Remove OmaBackups from this computer, as root (audit 10.2; 1.x
uninstall.sh): its services, its snapshots, its settings and keys; and the
backup itself only when asked twice (the gatekeeper's destroy, gate 20)."""

import os
import shutil
import subprocess

from omabackups.backup import progress
from omabackups.core import log, paths
from omabackups.core.errors import OmaError

UNITS = ("omabackups-backup.timer", "omabackups-health.timer")
JOBS = ("omabackups-backup@now", "omabackups-backup@scheduled", "omabackups-backup@anyway",
        "omabackups-backup@forced", "omabackups-restore", "omabackups-browse")


def remove(request: dict) -> dict:
    delete_backup = request.get("delete_backup") is True
    logger = log.get("remove")
    with progress.only_one() as mine:
        if not mine:
            raise OmaError("A backup is running.", "Wait for it to finish, or press Stop, then try again.",
                           code="busy")
        destroyed = delete_backup and _destroy(logger)
        for unit in UNITS:
            subprocess.run(["systemctl", "disable", "--now", unit], capture_output=True, check=False)
        for unit in JOBS:
            subprocess.run(["systemctl", "stop", f"{unit}.service"], capture_output=True, check=False)
        _snapshots(logger)
    for folder in (paths.system_state_dir(), paths.system_config_dir()):
        shutil.rmtree(folder, ignore_errors=True)
    paths.polkit_rule_file().unlink(missing_ok=True)
    logger.info("OmaBackups removed from this computer%s", " (and its backup)" if destroyed else "")
    return {"removed": True, "destroyed": destroyed}


def _destroy(logger) -> bool:
    from omabackups.where import location
    if not paths.server_file().exists():
        return False
    server = location.load()
    gate, _away = location.connect(server)
    if gate.call("version").get("gate", 0) < 20:
        raise OmaError("OmaBackups on your backup server needs updating before it can delete your backup.",
                       "Run: omabackups setup server --update, then Remove OmaBackups again. "
                       "Nothing was removed.", code="gate-version")
    gate.call("destroy", server["backup"])
    logger.info("the backup %s was deleted, every restore point in it", server["backup"][:12])
    return True


def _snapshots(logger) -> None:
    """Every snapshot OmaBackups kept on this computer, and their folder."""
    if os.environ.get("OMABACKUPS_SYSROOT"):
        return                                   # tests: never this computer's disks
    from omabackups.backup.source import SNAPSHOTS, Snapshots, parts
    for part in [p for p in parts() if p.btrfs]:
        with Snapshots(part.device) as snaps:
            for name in snaps.names():
                snaps.drop(name)
            subprocess.run(["btrfs", "subvolume", "delete", str(snaps.top / SNAPSHOTS)], capture_output=True)
        logger.info("%s: OmaBackups' snapshots removed", part.name)
