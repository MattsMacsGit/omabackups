"""Asking the root helper to do a job (BUILD 5.2, D27), from the user's side.

Write the request, start omabackups-root@<job>.service (the package's polkit
rule lets the linked user do that, no password), wait for it, read the result.
"""

import json
import os
import secrets
import subprocess
import sys

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic


def run(job: str, request: dict) -> dict:
    folder = paths.requests_dir()   # this user's own, private (D27)
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    os.chmod(folder.parent, 0o700)
    result_file = paths.results_dir() / f"{job}.json"
    # The result must carry this back: an old result from an earlier run
    # (which this user can't delete) is never mistaken for this one.
    nonce = secrets.token_hex(8)
    write_atomic(folder / f"{job}.json", json.dumps({**request, "nonce": nonce}).encode(), 0o600)

    if os.environ.get("OMABACKUPS_SYSROOT"):
        # Tests: the same root job, run directly (there is no systemd unit here).
        command = [sys.executable, "-m", "omabackups", "root-job", job]
    else:
        command = ["systemctl", "start", f"omabackups-root@{job}.service"]
    done = subprocess.run(command, capture_output=True, text=True)

    try:
        result = json.loads(result_file.read_text())
        if result.get("nonce") != nonce:
            raise ValueError("an old result")
    except (OSError, ValueError):
        if "authoriz" in done.stderr.lower() or "access denied" in done.stderr.lower():
            raise OmaError("OmaBackups isn't allowed to start its jobs on this computer yet.",
                           "Run setup again: it links this computer (asks for your password once).",
                           done.stderr.strip(), code="not-linked") from None
        raise OmaError("OmaBackups' root helper didn't finish its job.",
                       "Try again. The details say what systemd reported.",
                       (done.stderr or done.stdout).strip() or f"exit {done.returncode}",
                       code="root-job-failed") from None
    if not result.get("ok"):
        error = result.get("error", {})
        raise OmaError(error.get("what", "The root job failed."), error.get("todo", ""),
                       error.get("details", ""), code=error.get("code", "root-job-failed"))
    return result["answer"]
