"""`omabackups root-job NAME`: run by omabackups-root@NAME.service, as root.

Inputs come from /run/omabackups/requests/NAME.json, accepted only when the
linked user wrote it (owner checked, no links). The result goes to
/run/omabackups/results/NAME.json, readable only by that user (D27, 5.2).
"""

import json
import os
import stat

from omabackups.core import log, paths
from omabackups.core.errors import OmaError, unexpected
from omabackups.core.events import Events
from omabackups.core.state import write_atomic

MAX_REQUEST = 64 * 1024


def linked_uid() -> int:
    try:
        return int(json.loads(paths.linked_user_file().read_text())["uid"])
    except (OSError, ValueError, KeyError):
        raise OmaError("This computer isn't linked to OmaBackups yet.",
                       "Set up backups first (it links this computer).", code="not-linked") from None


def _not_theirs(where) -> OmaError:
    return OmaError("A request for this job didn't come from the linked user.",
                    "Nothing was done.", str(where), code="bad-request")


def _open_request_folder(uid: int) -> int:
    """Walk to the user's request folder one step at a time, never following
    a link, and every step owned by the linked user. Returns a folder handle."""
    base, parts = paths.user_requests_location(uid)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = os.open(base, flags)
    except OSError:
        raise OmaError("The request for this job is missing.", "Try again.",
                       str(base), code="no-request") from None
    for part in [None, *parts]:
        if part is not None:
            try:
                new = os.open(part, flags, dir_fd=fd)
            except OSError:
                os.close(fd)
                raise OmaError("The request for this job is missing.", "Try again.",
                               f"{base}/{part}", code="no-request") from None
            os.close(fd)
            fd = new
        info = os.fstat(fd)
        if info.st_uid != uid or info.st_mode & 0o022:
            os.close(fd)
            raise _not_theirs(base if part is None else f"{base}/.../{part}")
    return fd


def read_request(name: str, uid: int) -> dict:
    folder = _open_request_folder(uid)
    leaf = f"{name}.json"
    try:
        try:
            fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
        except OSError:
            raise OmaError("The request for this job is missing.", "Try again.",
                           leaf, code="no-request") from None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_size > MAX_REQUEST:
                raise _not_theirs(leaf)
            with os.fdopen(fd, "rb") as f:
                fd = -1
                raw = f.read()
        finally:
            if fd >= 0:
                os.close(fd)
            try:   # read once, never left lying about
                os.unlink(leaf, dir_fd=folder)
            except OSError:
                pass
    finally:
        os.close(folder)
    try:
        request = json.loads(raw)
    except ValueError:
        raise OmaError("The request for this job is damaged.", "Try again.", code="bad-request") from None
    if not isinstance(request, dict):
        raise OmaError("The request for this job is damaged.", "Try again.", code="bad-request")
    return request


def write_result(name: str, uid: int, result: dict) -> None:
    folder = paths.results_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    write_atomic(path, (json.dumps(result) + "\n").encode(), 0o600)
    if os.geteuid() == 0:   # hand it to the linked user (tests already are that user)
        os.chown(path, uid, -1)


def _jobs() -> dict:
    from omabackups.restore import browse, files
    from omabackups.root import (job_backup, job_disk, job_migrate, job_points, job_remove, job_rescue,
                                 job_server, job_skips)
    return {"migrate-join": job_migrate.join, "migrate-points": job_migrate.points,
            "migrate-info": job_migrate.info, "migrate-settings": job_migrate.settings,
            "migrate-here": job_migrate.here,
            "browse-open": browse.open_job, "browse-close": browse.close_job,
            "restore-files-start": files.start_job, "restore-files-stop": files.stop_job,
            "create-backup": job_server.create_backup, "create-disk": job_disk.create_disk,
            "start-over": job_disk.start_over, "set-skips": job_skips.set_skips,
            "keep": job_points.keep, "delete-point": job_points.delete, "rebuild-from": job_points.rebuild,
            "point-sizes": job_points.point_sizes, "change-password": job_points.change_password,
            "rescue-key": job_points.rescue_key, "backup-dry-run": job_backup.dry_run, "remove": job_remove.remove,
            "rescue-usb-write": job_rescue.write, "rescue-usb-refresh": job_rescue.refresh}


def run(args, events: Events) -> int:
    name = args.job
    jobs = _jobs()
    if name not in jobs:
        raise OmaError(f"There is no root job called '{name}'.", code="bad-job")
    uid = linked_uid()
    logger = log.get("root")
    nonce = ""
    try:
        request = read_request(name, uid)
        nonce = str(request.pop("nonce", ""))
        result = {"ok": True, "answer": jobs[name](request)}
        logger.info("root job %s done", name)
        code = 0
    except OmaError as exc:
        logger.error("root job %s: %s | %s", name, exc.what, exc.details)
        result, code = {"ok": False, "error": exc.as_dict()}, 1
    except Exception as exc:  # noqa: BLE001 - the user must still see what happened
        error = unexpected(exc)
        logger.error("root job %s: %s", name, error.details)
        result, code = {"ok": False, "error": error.as_dict()}, 1
    write_result(name, uid, {**result, "nonce": nonce})
    return code
