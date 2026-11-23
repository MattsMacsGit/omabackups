"""D59 (store review): Migrate's steps inside the home folder run in their own
process as the user, never as root."""

import os
import pwd
import subprocess

import pytest
from test_migrate_apply import fake_state, restore_point, run

from omabackups.core import asuser
from omabackups.core.errors import OmaError


def test_a_home_step_runs_in_its_own_process(tmp_path):
    """And runs this code, even where the package isn't installed (GitHub's runner)."""
    (tmp_path / "here").write_text("x")
    assert asuser.run("anyone", "missing", {"home": str(tmp_path), "items": ["here", "gone"]}) == ["~/gone"]


def test_only_the_named_steps_can_run():
    with pytest.raises(OmaError) as caught:
        asuser.run("anyone", "rm-everything", {})
    assert caught.value.code == "bad-job"


def test_a_step_that_fails_says_so(tmp_path):
    with pytest.raises(OmaError) as caught:
        asuser.run("anyone", "missing", {"home": str(tmp_path)})          # an argument missing
    assert caught.value.code == "home-step" and "items" in caught.value.details


def test_as_root_it_becomes_the_user_with_nothing_of_roots(monkeypatch):
    me = pwd.getpwuid(os.getuid())
    asked = {}

    def fake_run(command, **kw):
        asked.update(kw, command=command)
        os.write(kw["pass_fds"][0], b"[]")
        return subprocess.CompletedProcess(command, 0, None, b"")
    monkeypatch.setattr(asuser, "dropping", lambda: True)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("OMABACKUPS_SECRET_LOOKING", "x")
    asuser.run(me.pw_name, "missing", {"home": "/nowhere", "items": []})
    assert (asked["user"], asked["group"]) == (me.pw_uid, me.pw_gid)
    assert asked["extra_groups"] == os.getgrouplist(me.pw_name, me.pw_gid)   # the user's groups, not root's
    assert asked["env"]["HOME"] == me.pw_dir and "OMABACKUPS_SECRET_LOOKING" not in asked["env"]
    assert asked["command"][1:3] == ["-I", "-c"] and asked["cwd"] == "/"


def test_every_step_in_the_home_goes_through_the_user(sandbox, tmp_path, monkeypatch):
    real, tasks = asuser.run, []

    def recording(user, task, args):
        tasks.append((user, task))
        return real(user, task, args)
    monkeypatch.setattr(asuser, "run", recording)
    fake_state(sandbox)
    run(sandbox, restore_point(tmp_path))
    from omabackups.migrate import apply
    apply.kept(sandbox.home, sandbox.home / ".local/state/omabackups/replaced/x", tmp_path / "root-keep", "new")
    assert {t for _, t in tasks} >= {"rename", "missing", "kept"}
    assert {u for u, _ in tasks} == {"new"}


def test_the_merge_reads_and_writes_as_the_user(sandbox, tmp_path, monkeypatch):
    from omabackups.migrate import apply
    from test_migrate_apply import getter
    from test_migrate_merge import MINE, NEW_STOCK, OLD_STOCK
    point = restore_point(tmp_path)
    for rel, text in {"system/usr/share/omarchy/config/hypr/bindings.lua": OLD_STOCK,
                      "home/old/.config/hypr/bindings.lua": MINE}.items():
        (point / rel).parent.mkdir(parents=True, exist_ok=True)
        (point / rel).write_text(text)
    (sandbox.home / ".config/hypr").mkdir(parents=True)
    (sandbox.home / ".config/hypr/bindings.lua").write_text(NEW_STOCK)
    real, tasks = asuser.run, []
    monkeypatch.setattr(asuser, "run", lambda u, t, a: tasks.append(t) or real(u, t, a))
    fake_state(sandbox)
    item = {"path": ".config/hypr/bindings.lua", "stock": "usr/share/omarchy/config/hypr/bindings.lua",
            "kind": "lua"}
    done = apply.run(getter(point), sandbox.home, sandbox.sysroot, "old", "new", [], [], [], False,
                     lambda: None, [item])
    assert done["merged"] == [".config/hypr/bindings.lua"] and "merge" in tasks


def test_migrate_settings_asks_for_the_password():
    from omabackups.core.rootjob import PASSWORD_JOBS
    from omabackups.root.link import rule_text
    assert "migrate-settings" in PASSWORD_JOBS
    assert '"migrate-settings"' in rule_text("someone")
