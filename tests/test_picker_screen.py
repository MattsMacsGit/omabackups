"""The picker's real screen, driven in a pretend terminal (a pty)."""

import os
import pty
import select
import subprocess
import sys
import time

from conftest import SRC


def drive(sandbox, keys: list[bytes]) -> tuple[int, str]:
    for rel in ("Projects/a.py", "Videos/v.mp4", ".cache/junk"):
        (sandbox.home / rel).parent.mkdir(parents=True, exist_ok=True)
        (sandbox.home / rel).write_bytes(b"x" * 1000)
    main, child = pty.openpty()
    env = dict(os.environ, PYTHONPATH=str(SRC), TERM="xterm-256color", LINES="30", COLUMNS="100")
    proc = subprocess.Popen([sys.executable, "-m", "omabackups", "pick"], stdin=child, stdout=child,
                            stderr=child, env=env, close_fds=True)
    os.close(child)
    seen = b""

    def read(wait: float) -> None:
        nonlocal seen
        end = time.time() + wait
        while time.time() < end:
            ready, _, _ = select.select([main], [], [], 0.1)
            if ready:
                try:
                    seen += os.read(main, 65536)
                except OSError:
                    return
    read(1.5)
    for key in keys:
        os.write(main, key)
        read(0.6)
    code = proc.wait(timeout=10)
    read(0.3)
    os.close(main)
    return code, seen.decode("utf-8", "replace")


def test_the_picker_opens_moves_and_quits(sandbox):
    code, screen = drive(sandbox, [b"j", b"q"])
    assert code == 0
    assert "Choose what gets backed up" in screen
    assert "Projects" in screen and "Videos" in screen and "System" in screen
    assert "Space tick" in screen and "Nothing was changed." in screen


def test_changes_ask_before_quitting(sandbox):
    code, screen = drive(sandbox, [b" ", b"q", b"n"])
    assert code == 0 and "Save your changes?" in screen and "Nothing was changed." in screen


def test_the_picker_needs_a_terminal(sandbox):
    done = sandbox.run("pick")
    assert done.returncode == 1 and "needs a terminal" in done.stderr


def test_saving_reaches_the_list_backups_read(sandbox, monkeypatch):
    import json

    from omabackups.backup import skips
    from omabackups.core import paths
    monkeypatch.setenv("PKEXEC_UID", str(os.getuid()))
    from omabackups.setup import server
    server.link()                                    # root jobs need a linked user
    code, screen = drive(sandbox, [b" ", b"s"])      # skip the top row (the biggest), save
    assert code == 0 and "Saved. The next backup follows your choices" in screen
    saved = json.loads((paths.system_config_dir() / "skips.json").read_text())
    assert saved["format"] == 2 and ".cache" in saved["home"]       # defaults kept
    mine = [r for r in saved["home"] if r.startswith(f"/{sandbox.home.name}/")]
    assert len(mine) == 1 and skips.for_part("home").skipped(mine[0].lstrip("/"))
