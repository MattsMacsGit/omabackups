import json
import os

import pytest

from omabackups.core import paths, state
from omabackups.core.errors import OmaError


def test_missing_state_is_none(sandbox):
    assert state.read("setup") is None


def test_write_then_read(sandbox):
    state.write("setup", {"where": "server", "first_backup": False})
    assert state.read("setup") == {"where": "server", "first_backup": False}


def test_file_is_private_and_versioned(sandbox):
    state.write("setup", {"a": 1})
    path = paths.state_file("setup")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert json.loads(path.read_text())["version"] == state.VERSION


def test_no_temp_files_left_behind(sandbox):
    state.write("setup", {"a": 1})
    state.write("setup", {"a": 2})
    assert [p.name for p in paths.state_dir().iterdir()] == ["setup.json"]


def test_a_failed_write_keeps_the_old_file(sandbox, monkeypatch):
    state.write("setup", {"a": 1})

    def boom(*_):
        raise OSError("disk full")
    with monkeypatch.context() as patch, pytest.raises(OSError):
        patch.setattr(os, "replace", boom)
        state.write("setup", {"a": 2})
    assert state.read("setup") == {"a": 1}
    assert [p.name for p in paths.state_dir().iterdir()] == ["setup.json"]


def test_damaged_state_says_so_plainly(sandbox):
    paths.state_dir().mkdir(parents=True)
    paths.state_file("setup").write_text("{half a fi")
    with pytest.raises(OmaError) as caught:
        state.read("setup")
    assert caught.value.code == "bad-state"
    assert caught.value.todo and caught.value.details


def test_other_versions_are_refused(sandbox):
    paths.state_dir().mkdir(parents=True)
    paths.state_file("setup").write_text('{"version": 99}')
    with pytest.raises(OmaError):
        state.read("setup")


def test_remove(sandbox):
    state.write("setup", {})
    state.remove("setup")
    state.remove("setup")  # twice is fine
    assert state.read("setup") is None
