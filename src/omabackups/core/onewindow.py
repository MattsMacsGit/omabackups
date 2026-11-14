"""One window at a time for setup, Migrate and the Rescue USB: a second
press of the panel's button (or a second window) found the first still open
and ran it all again beside it (demo film, 14 Nov 2026). The second now says
so and closes. A lock on a file in this user's runtime folder: it goes when
the window closes, however it closes."""

import fcntl
import os
from contextlib import contextmanager

from omabackups.core import paths
from omabackups.core.errors import OmaError


@contextmanager
def only_one(what: str):
    folder = paths.runtime_dir()
    folder.mkdir(parents=True, exist_ok=True)
    fd = os.open(folder / "window.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OmaError(f"{what} is already open in another window.", "Finish it there.",
                           code="already-open") from None
        yield
    finally:
        os.close(fd)
