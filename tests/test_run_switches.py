"""The switches in Settings that change what a backup does: away from home
off never asks (D34); smart thinning off keeps every restore point (D35)."""

from test_run import away_setup, latest, same, world  # noqa: F401  (world: the fixture)

from omabackups.backup import run
from omabackups.core import config


def switch(name: str, on: bool) -> None:
    values = config.load()
    values[name] = on
    config.save(values)


def test_away_switched_off_never_asks(world, monkeypatch):
    srv, kid, bid, src, box = world
    away_setup(monkeypatch)
    switch("away.on", False)
    done = run.backup(source=src)              # no AwayWait, though the size isn't known
    assert done["away"] is True
    same(latest(box), src)


def test_thinning_switched_off_keeps_every_restore_point(world):
    srv, kid, bid, src, box = world
    points = box / "points"
    points.mkdir(exist_ok=True)
    old = ["001-2020-01-01-1000", "001-2020-01-01-1100", "001-2020-01-02-1000"]
    for name in old:
        (points / name).mkdir()
        (points / name / "point.json").write_text("{}")
    switch("thinning.on", False)
    result = run.backup(source=src)
    names = sorted(p.name for p in points.iterdir())
    assert set(old) <= set(names) and result["point"] in names
    assert not run.load_record()["thinned"]
