"""`omabackups backup --dry-run` as root (audit 2.8): the backup's check
step only, what a backup now would send and delete. Nothing is changed:
no to-do list kept, no snapshot left, nothing sent, the record untouched."""

from omabackups.backup import progress, run
from omabackups.core.errors import OmaError


def dry_run(request: dict) -> dict:
    with progress.only_one() as mine:
        if not mine:
            raise OmaError("A backup is running.", "Wait for it to finish, then try again.", code="busy")
        return {"parts": run.backup(dry_run=True)["dry_run"]}
