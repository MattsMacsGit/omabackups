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
    # Child processes (root jobs, link) run this source tree, not an installed copy.
    monkeypatch.setenv("PYTHONPATH", str(SRC))
    # Fake systemctl, nmcli, pgrep and Omarchy's commands: tests never touch
    # this computer's real services, processes or desktop (tests/fake_bin.py).
    fake, fake_bin = tmp_path / "fake", tmp_path / "fake-bin"
    fake.mkdir()
    fake_bin.mkdir()
    for name in FAKES:
        tool = fake_bin / name
        tool.write_text(f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(Path(__file__).parent)!r})\n"
                        f"import fake_bin\nsys.exit(fake_bin.main({name!r}))\n")
        tool.chmod(0o755)
    monkeypatch.setenv("OMABACKUPS_FAKE", str(fake))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    return Sandbox(home, sysroot, fake)


FAKES = ("systemctl", "nmcli", "pgrep", "pkill", "hyprctl", "omarchy-theme-set", "omarchy-theme-bg-set", "gh")


class Sandbox:
    def __init__(self, home: Path, sysroot: Path, fake: Path):
        self.home = home
        self.sysroot = sysroot
        self.fake = fake          # the fake commands' state (tests/fake_bin.py)

    def calls(self) -> list[str]:
        p = self.fake / "calls"
        return p.read_text().splitlines() if p.exists() else []

    def run(self, *args: str) -> subprocess.CompletedProcess:
        """Run the real omabackups command, in a fresh process, in the sandbox."""
        env = dict(os.environ, PYTHONPATH=str(SRC))
        return subprocess.run(
            [sys.executable, "-m", "omabackups", *args],
            env=env, capture_output=True, text=True, timeout=60,
        )


@pytest.fixture(autouse=True)
def quick_audit(request, monkeypatch):
    """Backups run the audit (Your changes to Omarchy). The real one reads the
    whole system (pacman, sizes): too slow to run in every backup test. Tests
    that check the audit itself ask for it with @pytest.mark.real_audit."""
    if request.node.get_closest_marker("real_audit"):
        return
    from omabackups.audit import model, scan

    def quick(user=None):
        return model.audit({"system": "omarchy", "version": "test"}, user or "test",
                           [model.item("app:test", "apps", "Test app", "package", ["test"])], {})
    monkeypatch.setattr(scan, "safely", quick)
