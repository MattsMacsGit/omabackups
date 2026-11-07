"""The skip list means the same to the change list as to rsync."""

import subprocess

import pytest

from omabackups.backup.skips import Skips

S = Skips(["/tmp", ".cache", "**/.local/share/Trash", ".var/app/*/cache", "# a comment", ""])


@pytest.mark.parametrize("path, skipped", [
    ("tmp", True), ("tmp/x", True), ("var/tmp", False), ("a/tmp", False),
    ("u/.cache", True), ("u/.cache/x/y", True), (".cache", True), ("u/.cached", False),
    ("u/.local/share/Trash/files/x", True), ("u/.local/share/Trashy", False),
    ("u/.var/app/org.x/cache/f", True), ("u/.var/app/org.x/data/f", False),
    ("u/Documents/a.txt", False),
])
def test_skipped(path, skipped):
    assert S.skipped(path) is skipped


def test_rsync_skips_exactly_the_same(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    files = ["tmp/x", "var/tmp/x", "a/tmp/x", "u/.cache/x/y", "u/.cached/x",
             "u/.local/share/Trash/files/x", "u/.local/share/Trashy/x",
             "u/.var/app/org.x/cache/f", "u/.var/app/org.x/data/f", "u/Documents/a.txt"]
    for f in files:
        (src / f).parent.mkdir(parents=True, exist_ok=True)
        (src / f).write_text("x")
    subprocess.run(["rsync", "-a", *S.rsync_rules(), f"{src}/", f"{dst}/"], check=True)
    for f in files:
        assert (dst / f).exists() is not S.skipped(f), f


def test_fingerprint_follows_the_list():
    assert Skips(["a", "b"]).fingerprint() == Skips(["b", "a"]).fingerprint()
    assert Skips(["a"]).fingerprint() != Skips(["a", "b"]).fingerprint()
