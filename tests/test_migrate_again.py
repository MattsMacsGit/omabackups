"""Run Migrate again (D44): what came over before shows "Already in" and is
never brought twice; the keybinding merge never adds a line twice; the first
".omabackups-before" copy is kept; folders named after the old home folder
get the new name; your own settings start ticked."""

import json
import os
import pty
import select
import subprocess
import sys
import time

from conftest import SRC

from omabackups.migrate import apply, brought, merge, rename
from test_migrate_apply import fake_state, getter, restore_point
from test_migrate_merge import NEW_STOCK, OLD_STOCK

# Like the 8f test: a block added at the end of the old file.
SNOOPY = OLD_STOCK + """
-- Snoopy test desktop: Super+Shift+Y says hello.
o.bind("SUPER + SHIFT + Y", "Snoopy says hello", "notify-send 'Snoopy' 'Suppertime!'")
"""
BIND = 'o.bind("SUPER + SHIFT + Y"'


def test_merging_twice_adds_your_lines_once():
    once, _ = merge.lua(OLD_STOCK, SNOOPY, NEW_STOCK)
    twice, unplaced = merge.lua(OLD_STOCK, SNOOPY, once)
    assert once.count(BIND) == 1 and twice == once and unplaced == []


def test_a_lone_bracket_already_in_the_file_still_comes_over():
    stock = "a = 1\n"
    mine = stock + "o.bind(\"SUPER + K\", \"x\", function()\n  go()\nend)\n"
    new = stock + "foo(function()\n  go()\nend)\n"
    text, _ = merge.lua(stock, mine, new)
    assert 'o.bind("SUPER + K"' in text


def _merge_run(sandbox, point):
    return apply.run(getter(point), sandbox.home, sandbox.sysroot, "old", "new", [], [], [], False,
                     lambda: None, [{"path": ".config/hypr/bindings.lua", "kind": "lua",
                                     "stock": "usr/share/omarchy/config/hypr/bindings.lua"}])


def test_migrate_run_twice_keeps_the_first_before_copy_and_adds_nothing(sandbox, tmp_path):
    point = restore_point(tmp_path)
    for rel, text in {"system/usr/share/omarchy/config/hypr/bindings.lua": OLD_STOCK,
                      "home/old/.config/hypr/bindings.lua": SNOOPY}.items():
        (point / rel).parent.mkdir(parents=True, exist_ok=True)
        (point / rel).write_text(text)
    here = sandbox.home / ".config/hypr/bindings.lua"
    here.parent.mkdir(parents=True)
    here.write_text(NEW_STOCK)
    fake_state(sandbox)
    _merge_run(sandbox, point)
    _merge_run(sandbox, point)
    assert here.read_text().count(BIND) == 1
    assert (sandbox.home / ".config/hypr/bindings.lua.omabackups-before").read_text() == NEW_STOCK


def test_folders_named_after_the_old_home_get_the_new_name(tmp_path):
    home = tmp_path / "home" / "new"
    projects = home / ".claude/projects"
    old_chats = projects / "-home-old-Projects-app"
    old_chats.mkdir(parents=True)
    (old_chats / "chat1.jsonl").write_text("one")
    (old_chats / "memory").mkdir()
    (old_chats / "memory/note.md").write_text("note")
    (projects / "-home-old").mkdir()
    (projects / "-home-older-Projects").mkdir()           # another user: not this one
    here = projects / f"{str(home).replace('/', '-')}-Projects-app"
    here.mkdir()
    (here / "chat2.jsonl").write_text("two")              # this system's own chat already
    (here / "memory").mkdir()
    done = rename.names(home, [".claude"], "/home/old")
    assert (here / "chat1.jsonl").read_text() == "one" and (here / "chat2.jsonl").read_text() == "two"
    assert (here / "memory/note.md").read_text() == "note"
    assert not old_chats.exists()
    assert (projects / str(home).replace("/", "-")).is_dir()
    assert (projects / "-home-older-Projects").is_dir()
    assert len(done) == 2


def test_a_name_clash_never_overwrites(tmp_path):
    home = tmp_path / "new"
    (home / "app").mkdir(parents=True)
    (home / "app/-home-old-x").write_text("old")
    mine = home / "app" / f"{str(home).replace('/', '-')}-x"
    mine.write_text("mine")
    rename.names(home, ["app"], "/home/old")
    assert mine.read_text() == "mine" and (home / "app/-home-old-x").read_text() == "old"


def test_what_came_over_is_recorded_per_backup_line(sandbox):
    assert brought.already("003-2026-11-09-1928") == set()
    brought.record("003-2026-11-09-1928", {"setting:shell"})
    brought.record("003-2026-11-10-0900", {"desktop:hypr/bindings.lua"})
    assert brought.already("003-2026-11-11-0000") == {"setting:shell", "desktop:hypr/bindings.lua"}
    assert brought.already("004-2026-11-11-0000") == set()              # another old computer


def test_only_what_really_came_over_counts():
    items = [{"id": "tool:x", "name": "x", "group": "apps"},
             {"id": "setting:shell", "name": "Terminal setup", "group": "settings"},
             {"id": "files:Music", "name": "Music", "group": "files", "paths": ["~/Music"]},
             {"id": "files:Work", "name": "Work", "group": "files", "paths": ["~/Work"]}]
    job = {"skipped": ["x: install it again by hand (y)"], "files": ["Music"]}
    picked = [i["id"] for i in items]
    assert brought.came_over(job, picked, items, True) == {"setting:shell", "files:Music"}
    assert brought.came_over(job, picked, items, False) == {"setting:shell"}     # folders later
    assert brought.restored({"files": ["Work"], "files_restored": True}) == {"files:Work"}
    assert brought.restored({"files": ["Work"], "files_restored": False}) == set()


CHANGES = {"groups": [{"id": "settings", "title": "Settings"}],
           "items": [{"id": "setting:shell", "group": "settings", "name": "Terminal setup", "suggest": "keep"},
                     {"id": "setting:git", "group": "settings", "name": "Git identity", "suggest": "keep"}]}

PICK = """
import json, sys
from omabackups.tui import migrate_pick
changes = json.loads(sys.argv[1])
got = migrate_pick.run(changes, "today", already={"setting:shell"})
print("RESULT", json.dumps(got))
"""


def test_the_picker_shows_already_in_and_wont_tick_it(sandbox):
    main, child = pty.openpty()
    env = dict(os.environ, PYTHONPATH=str(SRC), TERM="xterm-256color", LINES="30", COLUMNS="100")
    proc = subprocess.Popen([sys.executable, "-c", PICK, json.dumps(CHANGES)], stdin=child, stdout=child,
                            stderr=child, env=env, close_fds=True)
    os.close(child)
    seen = b""

    def read(wait):
        nonlocal seen
        end = time.time() + wait
        while time.time() < end:
            if select.select([main], [], [], 0.1)[0]:
                try:
                    seen += os.read(main, 65536)
                except OSError:
                    return
    read(1.5)
    for key in (b"a", b"a", b" ", b"s", b"y"):     # all/none twice, Space on the Already-in row, start
        os.write(main, key)
        read(0.5)
    proc.wait(timeout=10)
    read(0.3)
    os.close(main)
    screen = seen.decode("utf-8", "replace")
    assert "Already in" in screen
    result = json.loads(screen.split("RESULT", 1)[1].strip().splitlines()[0])
    assert result["picked"] == ["setting:git"]


def test_your_terminal_setup_starts_ticked():
    known = json.loads((SRC / "omabackups/audit/known.json").read_text())
    shell = next(s for s in known["settings"] if s["id"] == "shell")
    assert shell["suggest"] == "keep"


def test_an_older_restore_points_rows_get_this_versions_ticks():
    from omabackups.migrate import suggest
    old = {"items": [
        {"id": "setting:shell", "suggest": "you", "paths": ["~/.bashrc"]},
        {"id": "settings:omarchy-config/btop", "suggest": "you", "paths": ["~/.config/btop"]},
        {"id": "app:herdr", "suggest": "you", "paths": ["~/.config/herdr"], "source": {"refs": ["herdr"]}},
        {"id": "app:steam", "suggest": "you", "paths": ["~/.steam"], "source": {"refs": ["steam"]}},
        {"id": "app:nothing", "suggest": "you", "paths": [], "source": {"refs": ["nothing"]}},
        {"id": "setting:printers", "suggest": "you", "paths": ["/etc/cups/printers.conf"]}]}
    got = {i["id"]: i["suggest"] for i in suggest.today(old)["items"]}
    assert got == {"setting:shell": "keep", "settings:omarchy-config/btop": "keep", "app:herdr": "keep",
                   "app:steam": "you", "app:nothing": "you", "setting:printers": "you"}


def test_nearly_all_files_here_counts_as_in():
    from omabackups.migrate import here
    same = "".join(f".f          10 .config/chromium/f{n}\n" for n in range(19))
    one_changed = same + ">f..t...... 10 .config/chromium/Local State\n"        # 19 of 20 here
    fresh = ">f.st...... 10 .bashrc\n.f          10 .bash_profile\n"              # 1 of 2: not in
    listing = one_changed + fresh + "cd+++++++++ 0 .config/new/\n>f+++++++++ 5 .config/new/x\n"
    got = here.tally(listing, [".config/chromium", ".bashrc", ".bash_profile", ".config/new", ".config/gone"])
    assert got == {".config/chromium", ".bash_profile"}


def test_an_app_is_in_when_installed_and_its_settings_are_here():
    from omabackups.migrate import here
    changes = {"items": [
        {"id": "app:herdr", "group": "apps", "source": {"kind": "package", "refs": ["herdr"]},
         "paths": ["~/.config/herdr"]},
        {"id": "app:btop", "group": "apps", "source": {"kind": "package", "refs": ["btop"]}, "paths": []},
        {"id": "app:gone", "group": "apps", "source": {"kind": "package", "refs": ["gone"]}, "paths": []},
        {"id": "setting:shell", "group": "settings", "source": {"kind": "folder"},
         "paths": ["~/.bashrc", "~/.bash_history"]},
        {"id": "files:Music", "group": "files", "paths": ["~/Music"]}]}
    installed = ({"herdr", "btop"}, set())
    assert here.found(changes, {".bashrc"}, set(), installed) == {"app:btop"}
    assert here.found(changes, {".bashrc", ".bash_history", ".config/herdr", "Music"}, set(), installed) == \
        {"app:btop", "app:herdr", "setting:shell"}


def test_a_history_with_the_past_in_it_is_in():
    from omabackups.migrate import here
    old = "".join(f"old command {n}\n" for n in range(30))
    assert here.has_past(old, old + "typed since\n" * 5)                 # came over, then grew
    assert not here.has_past(old, "typed since\n" * 50)                  # blank, then typed in
    assert not here.has_past("", "anything\n")
    line = ">f.st...... 400 .bash_history\n.f          10 .bashrc\n"
    assert here.histories(line) == [".bash_history"]
    assert here.tally(line, [".bash_history", ".bashrc"], {".bash_history"}) == {".bash_history", ".bashrc"}
    assert here.tally(line, [".bash_history", ".bashrc"]) == {".bashrc"}


def test_an_app_you_log_in_to_is_in_when_installed_and_logged_in(monkeypatch):
    from omabackups.migrate import here
    changes = {"items": [{"id": "app:tailscale", "group": "apps", "paths": ["/var/lib/tailscale"],
                          "source": {"kind": "package", "refs": ["tailscale"]}}]}
    monkeypatch.setattr(here, "LOGGED_IN", {"tailscale": ["true"]})
    assert here.found(changes, set(), set(), ({"tailscale"}, set())) == {"app:tailscale"}
    monkeypatch.setattr(here, "LOGGED_IN", {"tailscale": ["false"]})
    assert here.found(changes, set(), set(), ({"tailscale"}, set())) == set()       # logged out
    monkeypatch.setattr(here, "LOGGED_IN", {"tailscale": ["true"]})
    assert here.found(changes, set(), set(), (set(), set())) == set()               # not installed
