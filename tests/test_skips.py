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


E = Skips(["/tmp", ".cache", "!/u/.cache", "/u/.cache/big", "/u/Videos/raw", "!/u/Videos/raw/keep"])


@pytest.mark.parametrize("path, skipped", [
    ("u/.cache", False), ("u/.cache/x", False),          # the exception
    ("u/.cache/big", True), ("u/.cache/big/y", True),    # a deeper skip inside it
    ("u/.cache/sub/.cache", True),                       # .cache elsewhere still skipped
    ("v/.cache", True),
    ("u/Videos/raw", True), ("u/Videos/raw/keep", True), # inside a skipped folder: stays skipped
])
def test_exceptions(path, skipped):
    assert E.skipped(path) is skipped


def test_rsync_agrees_with_exceptions(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    files = ["tmp/x", "u/.cache/x", "u/.cache/big/y", "u/.cache/sub/.cache/z", "v/.cache/w",
             "u/Videos/raw/keep/k", "u/Videos/raw/r", "u/Videos/ok"]
    for f in files:
        (src / f).parent.mkdir(parents=True, exist_ok=True)
        (src / f).write_text("x")
    subprocess.run(["rsync", "-a", *E.rsync_rules(), f"{src}/", f"{dst}/"], check=True)
    for f in files:
        assert (dst / f).exists() is not E.skipped(f), f


def test_why_names_the_rule_and_the_folder():
    assert E.why("v/.cache/w") == (".cache", "v/.cache")
    assert E.why("u/Videos/raw/keep") == ("/u/Videos/raw", "u/Videos/raw")
    assert E.why("u/Videos/ok") is None
