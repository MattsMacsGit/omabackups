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


def read_request(name: str, uid: int) -> dict:
    path = paths.requests_dir() / f"{name}.json"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise OmaError("The request for this job is missing.", "Try again.",
                       str(path), code="no-request") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_size > MAX_REQUEST:
            raise OmaError("A request for this job didn't come from the linked user.",
                           "Nothing was done.", str(path), code="bad-request")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            raw = f.read()
    finally:
        if fd >= 0:
            os.close(fd)
        path.unlink(missing_ok=True)   # read once, never left lying about
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
    from omabackups.root import job_server
    return {"create-backup": job_server.create_backup}


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
