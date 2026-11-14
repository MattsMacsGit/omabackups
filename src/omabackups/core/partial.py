"""Is this system whole yet? (SPEC-2.0.md §9; 1.x's partial-restore.json and
refuse_if_partial_restore, backup.sh:1104-1201.)

After a Quick Rescue, or a Migrate whose folders are still to come, those
folders are on the backup, not here: a backup now would delete them from the
backup's working copy (it did, 13 Nov 2026). So every backup waits until
every folder is back, or until a deliberate "Back up anyway" (Ctrl + click,
or `omabackups backup --force-after-restore`): that lifts the guard and the
restore point stays kept, holding what didn't come back.

What it reads:
- the user's migrate.json (written by Migrate, or by the rescue onto the new
  disk): the restore point and the folders still on the backup;
- restored.json (system state): each Restore my files run that finished,
  per restore point, written as root when it finished;
- backup.json's "forced_past": the restore point a forced backup went past.
"""

import json
import os
import pwd
from pathlib import Path

from omabackups.core import flow, paths, state
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic

RESTORED = "restored.json"
MAX_RUNS = 100


def restored_file() -> Path:
    return paths.system_state_dir() / RESTORED


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def note_restored(point: str, only: list[str] | None, leave_out: list[str] | None,
                  later: list[str] | None = None) -> None:
    """A Restore my files run finished (as root): what it brought back;
    `later`: the Quick skips items it brought (restore/later.py)."""
    data = _read(restored_file())
    runs = list(data.get(point) or [])[-(MAX_RUNS - 1):]
    runs.append({"only": only, "leave_out": list(leave_out or []), "later": list(later or [])})
    write_atomic(restored_file(), (json.dumps({**data, point: runs}, indent=1) + "\n").encode(), 0o644)


def is_back(folder: str, runs: list[dict]) -> bool:
    """A folder is back when a finished run brought all of it: everything, or
    the folder itself, with nothing inside it left out."""
    for run in runs:
        only, left = run.get("only"), run.get("leave_out") or []
        if (only is None or folder in only) and not any(
                rel == folder or rel.startswith(folder + "/") for rel in left):
            return True
    return False


def migrate_record() -> dict | None:
    """The linked user's migrate.json, read as that user or as root."""
    if os.geteuid() != 0 or os.environ.get("OMABACKUPS_SYSROOT"):
        try:
            return state.read(flow.MIGRATE)
        except OmaError:
            return None
    try:
        user = json.loads(paths.linked_user_file().read_text())["user"]
        home = Path(pwd.getpwnam(user).pw_dir)
        data = json.loads((home / ".local/state/omabackups" / f"{flow.MIGRATE}.json").read_text())
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def waiting(record: dict | None = None) -> dict | None:
    """The partial restore still waiting for its folders, or None when this
    system is whole: {"point", "folders" (still on the backup), "rescued"}."""
    mine = migrate_record()
    if not mine or not mine.get("done") or mine.get("files_restored"):
        return None
    if not mine.get("files") and not mine.get("later"):
        return None
    point = mine.get("point") or ""
    if record is None:
        record = _read(paths.system_state_dir() / "backup.json")
    if record.get("forced_past") == point:
        return None
    runs = _read(restored_file()).get(point) or []
    left = [f for f in mine.get("files") or [] if not is_back(f, runs)]
    if mine.get("later"):
        from omabackups.restore.later import label
        came = {i for run in runs for i in run.get("later") or []}
        left += [label(i) for i in mine["later"] if i not in came]
    if not left:
        return None
    return {"point": point, "folders": left, "rescued": bool(mine.get("rescued"))}


def refusal(left: dict) -> OmaError:
    folders = left["folders"]
    names = ", ".join(folders[:4]) + (f" and {len(folders) - 4} more" if len(folders) > 4 else "")
    return OmaError(
        "This system isn't whole yet, so backups are paused.",
        f"Your folders still on the backup ({names}) aren't on this system yet: backing up now would "
        "delete them from the backup's working copy. Bring them back first with Restore my files. "
        "To back up anyway and keep only what's here, hold Ctrl and press Back up now, or run: "
        f"omabackups backup --force-after-restore (restore point {left['point']} stays kept, "
        "with everything on it).",
        f"restored from {left['point']}; still on the backup: {', '.join(folders)}",
        code="partial-restore")
