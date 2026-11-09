"""Migrate's apply step, 1.x's order (D41): services swapped in and switched on
as the old system had them, the network never stopped, the old user name
fixed, a check that each thing is really back, apps closed first, and the
restart at the end. Fake systemctl/pgrep (tests/fake_bin.py)."""

import os
import shutil
from pathlib import Path

from omabackups.migrate import apply, finish, rename, running, services


def restore_point(tmp_path: Path, old_on: bool = True) -> Path:
    """A restore point's parts on disk: home/old and system."""
    point = tmp_path / "point"
    files = {"home/old/.config/app/conf": "path=/home/old/Documents\n",
             "home/old/.config/app/blob": "x\0/home/old/y",
             "home/old/.config/other/conf": "plain\n",
             "system/var/lib/tailscale/tailscaled.state": "logged-in",
             "system/etc/NetworkManager/system-connections/home.nmconnection": "wifi",
             "system/etc/thing.conf": "tweak"}
    for rel, data in files.items():
        p = point / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
    wants = point / "system/etc/systemd/system/multi-user.target.wants"
    wants.mkdir(parents=True)
    if old_on:
        (wants / "tailscaled.service").symlink_to("/usr/lib/systemd/system/tailscaled.service")
        (wants / "NetworkManager.service").symlink_to("/usr/lib/systemd/system/NetworkManager.service")
    os.symlink("/home/old/.config/app/conf", point / "home/old/.config/app/link")
    return point


def getter(point: Path):
    def get(part: str, items: list[str], dest: Path, owned: bool) -> str:
        for item in items:
            src = point / part / item
            if not src.exists() and not src.is_symlink():
                return f"{item}: No such file or directory"
            target = dest / item
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir() and not src.is_symlink():
                shutil.copytree(src, target, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.copy2(src, target, follow_symlinks=False)
        return ""
    return get


def fake_state(sandbox, units=(), active=()):
    (sandbox.fake / "units").write_text("".join(f"{u}\n" for u in units))
    (sandbox.fake / "active").write_text("".join(f"{u}\n" for u in active))


def run(sandbox, point, user="new", from_user="old", system=None, home=None):
    released = []
    done = apply.run(getter(point), sandbox.home, sandbox.sysroot, from_user, user,
                     home or [".config/app", ".config/other"],
                     system or ["var/lib/tailscale", "etc/NetworkManager", "etc/thing.conf"],
                     [], False, lambda: released.append(True))
    assert released == [True]
    return done


def test_a_service_that_was_on_comes_back_on_and_running(sandbox, tmp_path):
    point = restore_point(tmp_path)
    fake_state(sandbox, units=["tailscaled.service", "NetworkManager.service"],
               active=["NetworkManager.service"])
    done = run(sandbox, point)
    assert (sandbox.sysroot / "var/lib/tailscale/tailscaled.state").read_text() == "logged-in"
    ts = next(s for s in done["services"] if s["service"] == "tailscaled")
    assert ts["on"] and ts["running"] and ts["was_on"]
    assert "tailscaled.service" in (sandbox.fake / "enabled").read_text()
    calls = sandbox.calls()
    assert not any("stop NetworkManager" in c for c in calls)          # the network is never stopped
    assert any("reload NetworkManager.service" in c for c in calls)    # it reloads instead
    assert (sandbox.sysroot / "etc/thing.conf").read_text() == "tweak"
    assert not (sandbox.sysroot / "var/tmp").exists() or not any((sandbox.sysroot / "var/tmp").iterdir())


def test_a_running_service_is_stopped_while_its_settings_go_in(sandbox, tmp_path):
    point = restore_point(tmp_path)
    fake_state(sandbox, units=["tailscaled.service"], active=["tailscaled.service"])
    run(sandbox, point, system=["var/lib/tailscale"])
    calls = [c for c in sandbox.calls() if "tailscaled" in c]
    stop = next(i for i, c in enumerate(calls) if " stop " in f" {c} ")
    start = next(i for i, c in enumerate(calls) if " start " in f" {c} ")
    assert stop < start


def test_a_service_that_was_off_stays_off(sandbox, tmp_path):
    point = restore_point(tmp_path, old_on=False)
    fake_state(sandbox, units=["tailscaled.service"])
    done = run(sandbox, point, system=["var/lib/tailscale"])
    assert done["services"][0]["on"] is False and done["services"][0]["running"] is False
    assert not any(" enable " in f" {c} " or " start " in f" {c} " for c in sandbox.calls())


def test_a_service_not_installed_here_isnt_switched_on(sandbox, tmp_path):
    point = restore_point(tmp_path)
    fake_state(sandbox)                                   # no tailscaled here
    done = run(sandbox, point, system=["var/lib/tailscale"])
    assert done["services"][0]["on"] is False
    assert (sandbox.sysroot / "var/lib/tailscale/tailscaled.state").exists()   # its settings still come back


def test_the_old_user_name_is_fixed_in_text_settings_only(sandbox, tmp_path):
    point = restore_point(tmp_path)
    fake_state(sandbox)
    done = run(sandbox, point)
    conf = sandbox.home / ".config/app/conf"
    assert conf.read_text() == f"path={sandbox.home}/Documents\n"
    assert (sandbox.home / ".config/app/blob").read_bytes() == b"x\0/home/old/y"     # binary: left alone
    assert os.readlink(sandbox.home / ".config/app/link") == f"{sandbox.home}/.config/app/conf"
    assert sorted(done["renamed"]) == [".config/app/conf", ".config/app/link"]


def test_the_same_user_name_changes_nothing(sandbox, tmp_path):
    point = restore_point(tmp_path)
    fake_state(sandbox)
    done = run(sandbox, point, user="old")
    assert done["renamed"] == []
    assert (sandbox.home / ".config/app/conf").read_text() == "path=/home/old/Documents\n"


def test_rename_matches_whole_names_only(tmp_path):
    find = rename.pattern("/home/old")
    assert find.sub(b"/home/new", b"/home/oldie /home/old /home/old/x '/home/old'") == \
        b"/home/oldie /home/new /home/new/x '/home/new'"


def test_what_didnt_come_back_is_said(sandbox, tmp_path):
    point = restore_point(tmp_path)
    fake_state(sandbox)
    done = run(sandbox, point, home=[".config/app", ".config/not-there"], system=["etc/thing.conf"])
    assert any("~/.config/not-there isn't back" in p["what"] for p in done["problems"])


def test_the_old_systems_services_are_read_from_its_wants_folders(tmp_path):
    d = tmp_path / "system"
    (d / "multi-user.target.wants").mkdir(parents=True)
    (d / "bluetooth.target.wants").mkdir()
    (d / "multi-user.target.wants/tailscaled.service").touch()
    (d / "bluetooth.target.wants/bluetooth.service").touch()
    (d / "stray.service").touch()
    on = services.enabled(d)
    assert on == {"tailscaled.service", "bluetooth.service"}
    assert services.service_for("/var/lib/tailscale/x") == "tailscaled"
    assert services.service_for("etc/NetworkManager/system-connections/a") == "NetworkManager"
    assert services.service_for("/etc/thing.conf") is None


def test_browsers_are_closed_first(sandbox):
    apps = running.holders(["~/.config/chromium", "~/.config/app", "~/.config/Code/User"])
    assert [a[0] for a in apps] == ["Chromium", "VS Code"]
    (sandbox.fake / "running").write_text("chromium\n")
    assert running.still_open(apps, "new") == ["Chromium"]


def test_the_restart_comes_after_the_countdown_even_with_no_answer():
    said, rebooted = [], []
    finish.restart(said.append, lambda: rebooted.append(True), seconds=1)
    assert rebooted == [True]
    assert any("Omarchy will now restart" in s for s in said)
