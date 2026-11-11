"""The Rescue USB's system image (D16, 9c): downloaded when you make a stick,
never at install; its size said first; a stopped download carries on where
it stopped; checked against its published checksum before anything is
written; kept, so Refresh never downloads it again unless it's newer.

While testing it comes from the "rescue-edge" pre-release (built on GitHub by
.github/workflows/rescue.yml); at release each version has its own (stage 12).
"""

import hashlib
import subprocess
from pathlib import Path

from omabackups.core import paths
from omabackups.core.errors import OmaError

BASE = "https://github.com/MattsMacsGit/omabackups/releases/download/rescue-edge/"
NAME = "omabackups-rescue-x86_64.iso"


def folder() -> Path:
    return paths.cache_dir() / "rescue"


def path() -> Path:
    return folder() / NAME


def _curl(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["curl", "-fL", "--retry", "3", "--connect-timeout", "20", *args],
                          capture_output=capture, text=True)


def _unreachable(details: str) -> OmaError:
    return OmaError("The rescue system couldn't be downloaded.",
                    "Check the internet connection, then try again: it carries on where it stopped.",
                    details, code="rescue-download")


def published() -> dict:
    """The published image: its checksum and version (small files)."""
    sums = _curl("-s", BASE + NAME + ".sha256")
    if sums.returncode != 0 or not sums.stdout.split():
        raise _unreachable(sums.stderr.strip() or f"no checksum at {BASE}")
    version = _curl("-s", BASE + NAME.replace(".iso", ".version"))
    head = _curl("-sI", BASE + NAME)
    size = 0
    for line in head.stdout.splitlines():
        if line.lower().startswith("content-length:"):
            size = int(line.split(":", 1)[1].strip() or 0)      # the last one is the file's, after redirects
    return {"sha256": sums.stdout.split()[0].lower(), "version": version.stdout.strip(), "size": size}


def have(want: dict) -> bool:
    """The kept image is the published one (same checksum)."""
    marker = folder() / (NAME + ".sha256")
    return path().is_file() and marker.is_file() and marker.read_text().strip() == want["sha256"]


def download(want: dict) -> Path:
    """Fetch it (curl shows the progress; -C - carries on a stopped one), then
    check it. A file that doesn't match is moved aside, never written."""
    folder().mkdir(parents=True, exist_ok=True)
    partial = path().with_suffix(".part")
    done = _curl("-C", "-", "--progress-bar", "-o", str(partial), BASE + NAME, capture=False)
    if done.returncode not in (0, 33):          # 33: already complete (nothing to carry on)
        raise _unreachable(f"curl exit {done.returncode}")
    if checksum(partial) != want["sha256"]:
        partial.rename(partial.with_suffix(".bad"))
        raise OmaError("The downloaded rescue system didn't match its checksum, so it wasn't used.",
                       "Try again: it downloads it fresh.", f"expected {want['sha256']}", code="rescue-checksum")
    partial.replace(path())
    (folder() / (NAME + ".sha256")).write_text(want["sha256"] + "\n")
    (folder() / (NAME + ".version")).write_text(want.get("version", "") + "\n")
    return path()


def checksum(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while block := f.read(8 << 20):
            h.update(block)
    return h.hexdigest()
