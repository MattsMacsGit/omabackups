"""The desktop's extras and your automation (D46): a row only when there's
something of yours there; Omarchy's own and web apps left out; a crontab
brought back under the new user name; every row on this version's pages."""

import os
from pathlib import Path

from omabackups.audit import extras, packages, pages
from omabackups.migrate import apply


def found(home: Path) -> dict:
    return {i["id"]: i for i in extras.extras(home, "nobody-here", packages.Finder(home, set()))}


def test_only_whats_yours_is_listed(sandbox):
    home = sandbox.home
    (home / ".local/share/fonts").mkdir(parents=True)
    (home / ".local/share/fonts/ShortStack.ttf").write_text("font")
    (home / ".local/share/icons").mkdir(parents=True)                       # empty: not listed
    apps = home / ".local/share/applications"
    apps.mkdir(parents=True)
    (apps / "mine.desktop").write_text("[Desktop Entry]\nExec=mytool\n")
    (apps / "Grok.desktop").write_text("[Desktop Entry]\nExec=omarchy-launch-webapp https://grok.com\n")
    units = home / ".config/systemd/user"
    (units / "default.target.wants").mkdir(parents=True)
    (units / "sync.timer").write_text("[Timer]\n")
    os.symlink(units / "sync.timer", units / "default.target.wants/sync.timer")
    os.symlink("/usr/lib/systemd/user/x.service", units / "default.target.wants/x.service")   # a package's
    (home / ".config/gtk-3.0").mkdir(parents=True)
    (home / ".config/gtk-3.0/bookmarks").write_text("file:///home/u/Work Work\n")
    got = found(home)
    assert set(got) == {"extra:fonts", "extra:launchers", "extra:user-services", "extra:bookmarks"}
    assert got["extra:launchers"]["paths"] == ["~/.local/share/applications/mine.desktop"]
    assert sorted(got["extra:user-services"]["paths"]) == ["~/.config/systemd/user/default.target.wants/sync.timer",
                                                          "~/.config/systemd/user/sync.timer"]
    assert all(i["suggest"] == "keep" for i in got.values())


def test_every_row_has_a_page():
    rows = {"setting:ssh": "logins", "setting:ai-agents": "logins", "setting:chromium": "apps",
            "setting:shell": "terminal", "setting:local-bin": "terminal", "setting:printers": "tweaks",
            "settings:omarchy-config/btop": "apps", "app:x": "apps", "tool:uv:x": "apps",
            "desktop:hypr/bindings.lua": "desktop", "backgrounds:x": "backgrounds", "tweak:/etc/x": "tweaks",
            "extra:fonts": "desktop", "extra:crontab": "terminal", "extra:user-services": "terminal",
            "extra:flatpak-overrides": "apps", "files:Music": "files"}
    for rid, page in rows.items():
        assert pages.group_of({"id": rid}) == page, rid
    old = {"groups": [{"id": "settings", "title": "Settings"}],
           "items": [{"id": "setting:ssh", "group": "settings", "name": "SSH keys", "weight": 90}]}
    sorted_ = pages.sort(old)
    assert sorted_["items"][0]["group"] == "logins" and sorted_["groups"][0]["title"] == "Logins & keys"


def test_a_crontab_comes_back_under_the_new_user_name(sandbox):
    root = sandbox.sysroot
    (root / "var/spool/cron").mkdir(parents=True)
    (root / "var/spool/cron/old").write_text("0 * * * * backup-thing\n")
    assert apply.crontab(root, sandbox.home, "old", "new") == []
    assert (root / "var/spool/cron/new").read_text() == "0 * * * * backup-thing\n"
    assert not (root / "var/spool/cron/old").exists()
    (root / "var/spool/cron/old").write_text("other\n")
    assert apply.crontab(root, sandbox.home, "old", "new")                 # this user has one: said, not replaced
    assert (root / "var/spool/cron/new").read_text() == "0 * * * * backup-thing\n"
