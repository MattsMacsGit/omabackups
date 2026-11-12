"""The picker's logic on a pretend home (the screen is drawn from this)."""

import pytest

from omabackups.tui.pick_model import Model, Node


@pytest.fixture
def world(tmp_path):
    home, system = tmp_path / "home", tmp_path / "root"
    files = {"u/Projects/a.py": 300, "u/Videos/holiday.mp4": 5000, "u/Videos/render.mp4": 2000,
             "u/Downloads/big.iso": 9000, "u/.cache/junk": 700, "u/.config/app.conf": 50,
             "opt/tool/bin": 400}
    for rel, size in files.items():
        root = system if rel.startswith("opt") else home
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"x" * size)
    (system / "home").mkdir()
    import time
    later = int(time.time()) + 1000          # the restore point was made after these files
    record = {"last_finished": later, "last_point": "001-2026-11-07-1200",
              "point_skips": {
                  "001-2026-11-01-1200": {"time": later, "skips": {"home": [".cache"], "system": []}},
                  "001-2026-11-07-1200": {"time": later, "skips": {"home": ["/u/Downloads", ".cache"],
                                                                   "system": []}}},
              "space": {"used": 9000, "free": 1000}}
    rules = {"home": ["/u/Downloads", ".cache", "/u/Videos/render.mp4"], "system": []}
    return Model("u", record, roots={"home": home, "system": system}, rules=rules)


def names(model, node):
    return [n.name for n in model.children(node)]


def test_first_page(world):
    world.measure(world.home())
    shown = [n.name for n in world.listing(world.home())]
    assert shown == ["Downloads", "Videos", "Projects", "Quick skips"]     # hidden ones aren't shown...
    world.show_hidden = True                                               # ...until h
    assert [n.name for n in world.listing(world.home())] == ["Downloads", "Videos", "Projects",
                                                             ".cache", ".config", "Quick skips"]


def test_marks_colours_and_lines(world):
    m = world
    m.measure(m.home())
    videos, downloads = Node("home", "u/Videos", "Videos", True), Node("home", "u/Downloads", "Downloads", True)
    cache, render = Node("home", "u/.cache", ".cache", True), Node("home", "u/Videos/render.mp4", "render.mp4", False)
    assert (m.mark(videos), m.colour(videos)) == ("•", "green")
    assert m.explain(videos) == "Videos: 1 thing inside is skipped. Open it to see."
    # Downloads: skipped now, but an older restore point (11-01) has it: yellow.
    assert (m.mark(downloads), m.colour(downloads)) == (" ", "yellow")
    assert m.explain(downloads).startswith("Downloads: Not backed up any more, but in your older "
                                           "restore points until thinning removes them")
    assert "like every .cache" in m.explain(cache)
    assert m.colour(render) == "yellow"          # skipped since the latest; older points have it
    assert m.size(videos) == 5000                                  # only what's backed up


def test_space_ticks_and_skips(world):
    m = world
    downloads = Node("home", "u/Downloads", "Downloads", True)
    assert m.toggle(downloads) is None and not m.skipped(downloads)
    assert m.colour(downloads) == "blue"                           # ticked: goes at the next backup
    assert m.explain(downloads) == "Downloads: goes in at the next backup."
    assert "/u/Downloads" not in m.rules["home"] and m.dirty
    projects = Node("home", "u/Projects", "Projects", True)
    m.toggle(projects)
    assert m.skipped(projects) and "/u/Projects" in m.rules["home"]


def test_a_cache_can_be_backed_up_on_its_own(world):
    m = world
    cache = Node("home", "u/.cache", ".cache", True)
    m.toggle(cache)
    assert not m.skipped(cache) and "!/u/.cache" in m.rules["home"] and ".cache" in m.rules["home"]
    m.toggle(cache)
    assert m.skipped(cache) and "!/u/.cache" not in m.rules["home"]


def test_inside_a_skipped_folder(world):
    m = world
    iso = Node("home", "u/Downloads/big.iso", "big.iso", False)
    assert m.toggle(iso) == "It's inside Downloads, which is skipped: tick Downloads to back it up."
    assert m.explain(iso) == "big.iso: inside Downloads, which is skipped. Tick Downloads to back it up."


def test_sizes_follow_the_ticks_and_the_bottom_line(world):
    m = world
    m.measure(m.home()), m.measure(m.system())
    assert m.total() == 300 + 5000 + 50 + 400
    assert m.bottom() == ("Backing up 5.8 KB · your backup has 1.0 KB free", True)
    m.toggle(Node("home", "u/Downloads", "Downloads", True))
    m.measure(m.home())
    text, fits = m.bottom()
    assert text.startswith("Backing up 14.8 KB") and fits is False   # red: won't fit


def test_names_with_wildcards_only_match_themselves(world, tmp_path):
    m = world
    (tmp_path / "home/u/Photos [2024]").mkdir()
    (tmp_path / "home/u/Photos 2").mkdir()
    odd = Node("home", "u/Photos [2024]", "Photos [2024]", True)
    m.toggle(odd)
    assert m.skipped(odd) and not m.skipped(Node("home", "u/Photos 2", "Photos 2", True))


def quick_row(model, qid):
    return next(n for n in model.children(model.quick()) if n.rel == qid)


def test_quick_skips(world):
    m = world
    names_ = [n.name for n in m.children(m.quick())]
    assert names_[:4] == ["Downloads", "Caches", "Trash", "Package cache"] and "Game libraries" in names_
    caches = quick_row(m, "caches")
    m.rules["home"] += [".thumbnails", ".var/app/*/cache"]      # the full default set
    m._refresh()
    assert (m.mark(caches), m.colour(caches)) == (" ", "grey")
    assert m.explain(caches) == ("Caches: Made again whenever they're needed. Skipped: not in your "
                                 "backup. Space backs them up.")
    m.toggle(caches)
    assert ".cache" not in m.rules["home"] and ".thumbnails" not in m.rules["home"]
    assert m.mark(caches) == "✓" and m.colour(caches) == "blue"    # was skipped at the last backup


def test_the_downloads_switch_and_folder_are_one_rule(world):
    m = world
    downloads = quick_row(m, "downloads")
    assert m.mark(downloads) == " "                     # "/u/Downloads" is in the list already
    m.toggle(downloads)
    assert not m.skipped(Node("home", "u/Downloads", "Downloads", True))


def test_partly_skipped_switch(world):
    m = world
    m.rules["system"] = ["/var/lib/docker"]
    m._refresh()
    vms = quick_row(m, "vms")
    assert m.mark(vms) == "•" and "Part of it is skipped" in m.explain(vms)
    m.toggle(vms)
    assert m.mark(vms) == " " and "/var/lib/containers" in m.rules["system"]


def test_quick_sizes_are_what_they_hold(world, tmp_path):
    m = world
    m.measure(m.quick())
    assert m.size(quick_row(m, "caches")) == 700            # skipped, but its size still shows
    assert m.size(quick_row(m, "downloads")) == 9000
    assert "always backed up" in m.explain(m.quick())


def test_folders_come_before_files(world, tmp_path):
    """Folders, then files, each biggest on the computer first: the skipped
    Downloads is still the biggest folder."""
    (tmp_path / "home/u/huge-file.bin").write_bytes(b"x" * 50_000)
    world.measure(world.home())
    shown = [n.name for n in world.listing(world.home())]
    assert shown == ["Downloads", "Videos", "Projects", "huge-file.bin", "Quick skips"]


def test_ticking_never_moves_a_row(world):
    """Rows sorted by what's backed up jumped about as they were ticked."""
    world.measure(world.home())
    before = [n.name for n in world.listing(world.home())]
    for name in ("Videos", "Downloads", "Projects"):
        world.toggle(Node("home", f"u/{name}", name, True))
        world.measure(world.home())
        assert [n.name for n in world.listing(world.home())] == before, name
    videos = Node("home", "u/Videos", "Videos", True)
    assert world.size(videos) == 0 and world.disk_size(videos) == 7000   # shown: backed up; order: real


def test_the_four_looks(world, tmp_path):
    m = world
    projects = Node("home", "u/Projects", "Projects", True)
    assert (m.mark(projects), m.colour(projects)) == ("✓", "green")     # in, staying
    m.toggle(projects)
    assert (m.mark(projects), m.colour(projects)) == (" ", "yellow")    # in older points, not any more
    import os
    import time
    (tmp_path / "home/u/New").mkdir()
    after = time.time() + 5000                 # made after the restore points
    os.utime(tmp_path / "home/u/New", (after, after))
    new = Node("home", "u/New", "New", True)
    m.toggle(new)
    assert m.colour(new) == "grey"                                     # never in any restore point
    m.toggle(new)
    assert (m.mark(new), m.colour(new)) == ("✓", "blue")               # ticked: goes next time


def test_caches_deep_inside_dont_make_a_folder_partly_skipped(world, tmp_path):
    """A folder said "2 things inside are skipped": caches, folders deep. The
    built-in and Quick skips are explained once, under Quick skips."""
    for rel in ("u/Projects/app/.cache/x", "u/Projects/app/sub/.cache/y"):
        (tmp_path / "home" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "home" / rel).write_bytes(b"c" * 10)
    world.measure(world.home())
    projects = Node("home", "u/Projects", "Projects", True)
    assert world.inside_skipped(projects) == 0 and world.mark(projects) == "✓"
    assert world.explain(projects) == "Projects: everything in it is backed up."
    videos = Node("home", "u/Videos", "Videos", True)          # your own skip still shows
    assert world.explain(videos) == "Videos: 1 thing inside is skipped. Open it to see."


def test_things_you_can_see_still_count_however_they_were_skipped(world, tmp_path):
    """Only hidden things drop out of the count: a visible folder left out by
    a built-in rule (lost+found) still makes its folder partly skipped."""
    (tmp_path / "home/u/Projects/lost+found").mkdir(parents=True)
    (tmp_path / "home/u/Projects/lost+found/x").write_bytes(b"l")
    world.rules["home"].append("lost+found")                    # a built-in rule
    world._refresh()
    world.measure(world.home())
    projects = Node("home", "u/Projects", "Projects", True)
    assert world.inside_skipped(projects) == 1 and world.mark(projects) == "•"
