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
    record = {"last_finished": 1, "skip_patterns": {"home": ["/u/Downloads", ".cache"], "system": []},
              "space": {"used": 9000, "free": 1000}}
    rules = {"home": ["/u/Downloads", ".cache", "/u/Videos/render.mp4"], "system": []}
    return Model("u", record, roots={"home": home, "system": system}, rules=rules)


def names(model, node):
    return [n.name for n in model.children(node)]


def test_first_page(world):
    world.measure(world.home())
    assert names(world, world.home()) == ["Videos", "Projects", "Downloads", ".config", ".cache", "System"]
    assert "home" not in names(world, world.system())          # mount points aren't offered


def test_marks_colours_and_lines(world):
    m = world
    m.measure(m.home())
    videos, downloads = Node("home", "u/Videos", "Videos", True), Node("home", "u/Downloads", "Downloads", True)
    cache, render = Node("home", "u/.cache", ".cache", True), Node("home", "u/Videos/render.mp4", "render.mp4", False)
    assert (m.mark(videos), m.colour(videos)) == ("•", "green")
    assert m.explain(videos) == "Videos: 1 thing inside is skipped. Open it to see."
    assert (m.mark(downloads), m.colour(downloads)) == (" ", "grey")
    assert m.explain(downloads) == "Downloads: skipped. Space backs it up again."
    assert "like every .cache" in m.explain(cache)
    assert m.explain(render) == "render.mp4: skipped. Space backs it up again."
    assert m.size(videos) == 5000                                  # only what's backed up


def test_space_ticks_and_skips(world):
    m = world
    downloads = Node("home", "u/Downloads", "Downloads", True)
    assert m.toggle(downloads) is None and not m.skipped(downloads)
    assert m.colour(downloads) == "blue"                           # goes at the next backup
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
    assert "Tick that first" in m.toggle(iso)
    assert "inside Downloads" in m.explain(iso)


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
