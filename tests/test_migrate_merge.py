"""Keybindings, bar & theme are merged, never copied (D43), the way the 5 Nov
hand merge did it: your own lines on top of this release's file, a comma-list
setting joined onto the NEW default, your bar with the new release's
additions kept, plugins you didn't bring left out, the theme applied by name,
and files Hyprland rejects put back."""

import json

from omabackups.migrate import desktop, merge, plan

OLD_STOCK = """-- Keep only your personal keybinding overrides here.

-- Add a new binding.
-- o.bind("SUPER + SHIFT + R", "SSH", "alacritty -e ssh your-server")

-- Disable a default binding without replacing it.
-- hl.unbind("SUPER + SHIFT + B")
"""
MINE = OLD_STOCK + """
-- Swap the AI web apps
hl.unbind("SUPER + SHIFT + A")
o.bind("SUPER + SHIFT + A", "Grok", { webapp = "https://grok.com" })
"""
NEW_STOCK = OLD_STOCK.replace("-- Add a new binding.", "-- Add a new binding (see the manual).") + \
    '\n-- Logitech MX Keys examples:\n-- o.bind("SUPER + H", nil, "voxtype record toggle")\n'


def test_your_bindings_go_on_top_of_this_releases_file():
    text, unplaced = merge.lua(OLD_STOCK, MINE, NEW_STOCK)
    assert unplaced == []
    assert text.startswith(NEW_STOCK.rstrip("\n"))                 # the new file stays as it is
    assert 'o.bind("SUPER + SHIFT + A", "Grok"' in text
    assert text.count('hl.unbind("SUPER + SHIFT + A")') == 1
    assert "Logitech MX Keys" in text                              # the new release's part kept


def test_nothing_of_yours_means_the_new_file_unchanged():
    text, unplaced = merge.lua(OLD_STOCK, OLD_STOCK, NEW_STOCK)
    assert text == NEW_STOCK and unplaced == []


def test_a_comma_list_keeps_the_new_default_and_adds_yours():
    old = '  kb_options = "compose:caps",\n'
    mine = '  kb_options = "compose:caps,srvrkeys:none",\n'
    new = '  kb_options = "omarchy:shift_caps_compose",\n'
    wrap = "hl.config({{ input = {{\n{}}} }})\n"
    text, unplaced = merge.lua(wrap.format(old), wrap.format(mine), wrap.format(new))
    assert 'kb_options = "omarchy:shift_caps_compose,srvrkeys:none"' in text and unplaced == []


def test_a_changed_line_this_release_no_longer_has_is_listed_not_forced():
    old = "local scale = 1\nhl.monitor({ scale = scale })\n"
    mine = "local scale = 2\nhl.monitor({ scale = scale })\n"
    new = 'local omarchy_monitor_scale = "auto"\nhl.monitor({ scale = omarchy_monitor_scale })\n'
    text, unplaced = merge.lua(old, mine, new)
    assert text == new and unplaced == ["local scale = 2"]


BAR_STOCK = {"bar": {"background": "opaque", "layout": {"right": [{"id": "omarchy.tray"}, {"id": "omarchy.network"}]}},
             "plugins": [], "version": 1}
BAR_MINE = {"bar": {"background": "none", "layout": {"right": [
    {"id": "omarchy.tray"}, {"id": "oma.backups"}, {"id": "someone.weather"},
    {"id": "omarchy.power", "showPercentage": True}, {"id": "omarchy.network"}]}},
    "plugins": [{"id": "someone.wallpaper"}, {"id": "someone.weather"}], "version": 1}
BAR_NEW = {"bar": {"background": "opaque", "dock": {"show": True}, "layout": {"right": [
    {"id": "omarchy.tray"}, {"id": "omarchy.superwhisper"}, {"id": "omarchy.network"}]}},
    "plugins": [], "version": 1}


def test_the_bar_is_yours_with_the_new_releases_additions():
    keep = lambda wid: wid.startswith("omarchy.") or wid in {"oma.backups", "someone.wallpaper"}  # noqa: E731
    got = json.loads(merge.shell(json.dumps(BAR_STOCK), json.dumps(BAR_MINE), json.dumps(BAR_NEW), keep))
    assert got["bar"]["background"] == "none"                         # yours
    assert got["bar"]["dock"] == {"show": True}                       # new in this release
    right = [w["id"] for w in got["bar"]["layout"]["right"]]
    assert right == ["omarchy.tray", "oma.backups", "omarchy.power", "omarchy.network", "omarchy.superwhisper"]
    assert got["bar"]["layout"]["right"][2]["showPercentage"] is True
    assert got["plugins"] == [{"id": "someone.wallpaper"}]          # a plugin left behind stays out


def test_the_plan_merges_omarchys_files_and_applies_the_theme():
    changes = {"items": [
        {"id": "a", "group": "desktop", "paths": ["~/.config/hypr/bindings.lua"], "source": {}},
        {"id": "b", "group": "desktop", "paths": ["~/.config/omarchy/shell.json"], "source": {}},
        {"id": "c", "group": "desktop", "paths": ["~/.local/state/omarchy/current/theme.name"], "source": {}},
        {"id": "d", "group": "desktop", "paths": ["~/.config/omarchy/themes/mine"], "source": {}}]}
    job = plan.jobs(changes, {"a", "b", "c", "d"})
    assert [m["kind"] for m in job["merge"]] == ["lua", "json"]
    assert job["merge"][0]["stock"] == "usr/share/omarchy/config/hypr/bindings.lua"
    assert job["theme"] is True and job["home"] == ["~/.config/omarchy/themes/mine"]


def test_the_theme_is_applied_by_name_with_its_old_background(sandbox):
    pics = sandbox.home / ".config/omarchy/backgrounds/jade-horse"
    pics.mkdir(parents=True)
    (pics / "mine.png").write_bytes(b"png")
    said = []
    problems = desktop.theme({"name": "jade-horse", "background": "/home/old/.config/omarchy/backgrounds/jade-horse/mine.png"},
                             "old", sandbox.home, said.append)
    assert problems == []
    calls = sandbox.calls()
    assert "omarchy-theme-set jade-horse" in calls
    assert f"omarchy-theme-bg-set {pics / 'mine.png'}" in calls


def test_merged_files_hyprland_rejects_are_put_back(sandbox):
    hypr = sandbox.home / ".config/hypr"
    hypr.mkdir(parents=True)
    (hypr / "bindings.lua").write_text("merged\n")
    (hypr / "bindings.lua.omabackups-before").write_text("as it was\n")
    (sandbox.fake / "configerrors").write_text("bindings.lua:3: unexpected symbol\n")
    problems = desktop.check_hyprland([".config/hypr/bindings.lua"], sandbox.home)
    assert (hypr / "bindings.lua").read_text() == "as it was\n"
    assert (hypr / "bindings.lua.from-old-system").read_text() == "merged\n"
    assert "unexpected symbol" in problems[0]["details"]


def test_an_older_omarchys_theme_is_found_in_its_old_place(tmp_path):
    """Before June 2026 the theme in use lived in ~/.config/omarchy/current,
    as a link to the theme's folder (D42)."""
    import os
    from omabackups.audit import omarchy
    from omabackups.migrate import apply
    home = tmp_path / "home/old"
    cur = home / ".config/omarchy/current"
    cur.mkdir(parents=True)
    os.symlink("/home/old/.config/omarchy/themes/tokyo-night", cur / "theme")
    os.symlink("/home/old/.config/omarchy/current/theme/backgrounds/1.jpg", cur / "background")
    items = {i["id"]: i for i in omarchy.desktop(home)}
    assert items["desktop:theme-current"]["name"] == "Theme: tokyo-night"
    path = items["desktop:theme-current"]["paths"][0]
    assert plan.THEME.match(path)

    def get(part, rels, dest, owned):
        for rel in rels:
            src = tmp_path / "home" / part.split("/", 1)[1] / rel
            if src.is_symlink() or src.exists():
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                os.symlink(os.readlink(src), dest / rel) if src.is_symlink() else None
        return "some missing"
    found = apply._theme(get, "old", tmp_path / "stage")
    assert found == {"name": "tokyo-night", "background": "/home/old/.config/omarchy/current/theme/backgrounds/1.jpg"}
