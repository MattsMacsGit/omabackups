"""State files: small JSON files that remember what has been done.

Rule (BUILD 8.2): a state file is written only AFTER the step it describes
succeeded. Writes are atomic: a power cut leaves either the old file or the
new one, never half of one.
"""

import json
import os
import tempfile
from pathlib import Path

from omabackups.core import paths
from omabackups.core.errors import OmaError

VERSION = 1


def write_atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def read(name: str) -> dict | None:
    """The saved state called `name`, or None if there is none yet."""
    path = paths.state_file(name)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OmaError(
            f"OmaBackups' saved state '{name}' is damaged.",
            "Run the step that made it again. If that doesn't help, "
            "Start over from Settings.",
            f"{path}: {exc}",
            code="bad-state",
        ) from exc
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise OmaError(
            f"OmaBackups' saved state '{name}' is from a different version.",
            "Update OmaBackups, or Start over from Settings.",
            f"{path}: version {data.get('version') if isinstance(data, dict) else '?'}",
            code="bad-state",
        )
    data = dict(data)
    del data["version"]
    return data


def write(name: str, data: dict) -> None:
    """Save state `name`. Call only after the step it describes succeeded."""
    body = {"version": VERSION, **data}
    text = json.dumps(body, indent=2, sort_keys=True) + "\n"
    write_atomic(paths.state_file(name), text.encode("utf-8"))


def remove(name: str) -> None:
    try:
        paths.state_file(name).unlink()
    except FileNotFoundError:
        pass
