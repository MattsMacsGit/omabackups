"""Your changes to Omarchy: the audit (D9, D21)."""

import json
import time

import pytest

from omabackups.audit import model, omarchy, scan


@pytest.fixture
def fake_omarchy(tmp_path, monkeypatch):
    stock = tmp_path / "share"
    for rel, text in {"config/hypr/bindings.lua": "stock binds", "config/hypr/monitors.lua": "stock",
                      "config/omarchy/shell.json": "{}", "config/btop/btop.conf": "stock",
                      "applications/HEY.desktop": "[Desktop Entry]"}.items():
        (stock / rel).parent.mkdir(parents=True, exist_ok=True)
        (stock / rel).write_text(text)
    monkeypatch.setattr(omarchy, "SHARE", stock)
    home = tmp_path / "home"
    for rel, text in {
        ".config/hypr/bindings.lua": "MY binds", ".config/hypr/monitors.lua": "stock",
        ".config/hypr/extra.lua": "mine", ".config/omarchy/shell.json": "{}",
        ".config/omarchy/themes/sunset/colors.toml": "x",
        ".config/omarchy/backgrounds/sunset/beach.jpg": "jpg",
        ".local/state/omarchy/current/theme.name": "sunset\n",
        ".config/btop/btop.conf": "changed",
        ".local/share/applications/HEY.desktop": "Exec=omarchy-launch-webapp https://hey.com",
        ".local/share/applications/Notes.desktop": "Name=Notes\nExec=omarchy-launch-webapp https://x",
    }.items():
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(text)
    return home


def ids(items):
    return {i["id"] for i in items}


def test_the_desktop_differences_are_found(fake_omarchy):
    found = omarchy.desktop(fake_omarchy)
    got = ids(found)
    assert "desktop:hypr/bindings.lua" in got          # changed
    assert "desktop:hypr/monitors.lua" not in got      # same as Omarchy's
    assert "desktop:hypr/extra.lua" in got             # one you added
    assert "desktop:shell" not in got                  # same as Omarchy's
    assert {"desktop:theme/sunset", "desktop:theme-current", "backgrounds:sunset"} <= got
    btop = next(i for i in found if i["id"] == "settings:omarchy-config/btop")
    assert btop["suggest"] == "you"                    # could be the app saving its own state
    binds = next(i for i in found if i["id"] == "desktop:hypr/bindings.lua")
    assert binds["name"] == "Keybindings" and binds["suggest"] == "keep" and binds["paths"][0].startswith("~/")


def test_already_listed_settings_arent_repeated(fake_omarchy):
    found = omarchy.desktop(fake_omarchy, claimed={fake_omarchy / ".config/btop"})
    assert "settings:omarchy-config/btop" not in ids(found)


def test_only_your_own_web_apps(fake_omarchy):
    assert ids(omarchy.webapps(fake_omarchy)) == {"webapp:Notes"}


def test_the_format_is_neutral_and_ordered():
    items = [model.item("files:Documents", "files", "Documents", "folder"),
             model.item("app:a", "apps", "A", "package", ["a"], weight=10),
             model.item("app:b", "apps", "B", "package", ["b"], weight=90)]
    a = model.audit({"system": "omarchy", "version": "4"}, "u", items, {})
    assert [i["id"] for i in a["items"]] == ["app:b", "app:a", "files:Documents"]
    assert a["format"] == model.FORMAT and a["source"]["system"] == "omarchy"
    assert [g["title"] for g in a["groups"]][:3] == ["Apps", "Settings", "System tweaks"]
    with pytest.raises(AssertionError):
        model.item("x", "nonsense", "X", "file")


@pytest.mark.real_audit
def test_the_real_audit_runs_quickly_and_well_formed(sandbox):
    started = time.monotonic()
    a = scan.scan()
    assert time.monotonic() - started < 30
    assert a["format"] == model.FORMAT and a["source"]["system"] == "omarchy"
    for i in a["items"]:
        assert {"id", "group", "name", "suggest", "source", "paths", "why", "back"} <= set(i)
    json.dumps(a)       # it can be written as changes.json


@pytest.mark.real_audit
def test_the_audit_survives_missing_programs(sandbox, tmp_path, monkeypatch):
    """On a system without pacman, pactree or Omarchy's commands (GitHub's runner
    found this), the audit reports less, never crashes."""
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
    a = scan.scan()
    assert a["format"] == model.FORMAT
