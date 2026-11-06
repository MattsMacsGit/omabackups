"""The test harness.

`sandbox`: a fake home and fake system folders, so no test ever reads or
writes the real ones. Faking HOME isn't enough: every XDG_* variable is
cleared too, or paths would still point at the real folders.

Rule: tests never stub the output helpers (Events, log). They read what
really reached stdout/stderr; that's how a log line on stdout gets caught.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
FAKE_MACHINE_ID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    home = tmp_path / "home"
    sysroot = tmp_path / "sys"
    home.mkdir()
    (sysroot / "etc").mkdir(parents=True)
    (sysroot / "etc" / "machine-id").write_text(FAKE_MACHINE_ID + "\n")

    for var in list(os.environ):
        if var.startswith("XDG_"):
            monkeypatch.delenv(var)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OMABACKUPS_SYSROOT", str(sysroot))
    return Sandbox(home, sysroot)


class Sandbox:
    def __init__(self, home: Path, sysroot: Path):
        self.home = home
        self.sysroot = sysroot

    def run(self, *args: str) -> subprocess.CompletedProcess:
        """Run the real omabackups command, in a fresh process, in the sandbox."""
        env = dict(os.environ, PYTHONPATH=str(SRC))
        return subprocess.run(
            [sys.executable, "-m", "omabackups", *args],
            env=env, capture_output=True, text=True, timeout=60,
        )
