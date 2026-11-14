"""Every folder's size beside each restore point (audit 5.4): walked once by
the Pi after a backup, only the changed folders after an everyday one, read
by Choose what comes back at once. And `files` / `copy` (audit 5.2)."""

import gzip
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

from test_run import latest, world  # noqa: F401  (world: the fixture)

from omabackups.backup import run, skips
from omabackups.commands import files as files_cmd
from omabackups.core import rootjob
from omabackups.core.events import Events
from omabackups.tui import quick
from omabackups.tui import sizes as tui_sizes

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "gate"))
import sizes as gate_sizes  # noqa: E402


def listed(box: Path, point: str) -> dict:
    with gzip.open(box / "sizes" / f"{point}.json.gz", "rt") as f:
        return json.load(f)["parts"]


def tree(tmp_path: Path, files: dict) -> Path:
    for rel, size in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"x" * size)
    return tmp_path


def test_a_walk_counts_every_folder(tmp_path):
    top = tree(tmp_path / "t", {"u/a.txt": 10, "u/Docs/b.txt": 20, "u/Docs/deep/c.txt": 30, "v/d": 5})
    got = gate_sizes.walk(top)
    assert got[""] == [65, 4] and got["u"] == [60, 3] and got["u/Docs"] == [50, 2] and got["v"] == [5, 1]


def test_an_update_matches_a_whole_walk(tmp_path):
    top = tree(tmp_path / "t", {"u/a.txt": 10, "u/Docs/b.txt": 20, "u/Old/x": 7, "u/Keep/y": 3})
    before = gate_sizes.walk(top)
    shutil.rmtree(top / "u/Old")                             # deleted
    (top / "u/Docs/b.txt").write_bytes(b"x" * 25)            # changed
    tree(top, {"u/New/deep/z": 40})                          # a new folder, inside it more
    (top / "u/Keep").rename(top / "u/Kept")                  # moved
    dirty = ["u/Docs", "u", "u/New/deep", "u/Old", "u/Keep", "u/Kept"]
    assert gate_sizes.update(top, before, dirty) == gate_sizes.walk(top)


def test_each_backup_leaves_a_list_and_an_everyday_one_only_updates(world):  # noqa: F811
    srv, kid, bid, src, box = world
    first = run.backup(source=src)["point"]
    assert listed(box, first)["home"]["u"] == [5, 1]                   # notes.txt (.cache is skipped)
    (src.root / "home/u/Big").mkdir()
    (src.root / "home/u/Big/film.mkv").write_bytes(b"F" * 70_000)
    (src.root / "home/u/notes.txt").write_text("changed, much longer than before")
    second = run.backup(source=src)["point"]
    home = listed(box, second)["home"]
    whole = gate_sizes.walk(latest(box) / "home")
    assert home == whole and home["u/Big"] == [70_000, 1]
    ready = srv.ok(kid, f"sizes {bid} {second}")
    assert ready["ready"] and ready["parts"]["home"]["u/Big"] == [70_000, 1]


def test_the_picker_reads_sizes_from_the_list():
    folders = {"u": [1000, 9], "u/Videos": [700, 3], "u/Videos/old": [500, 1], "u/.cache": [100, 2],
               "u/Docs": [200, 4], "u/.ollama/models": [90, 1]}
    left = skips.Skips(["/u/Videos/old", ".cache"])
    assert tui_sizes.from_list(folders, "u", left, lambda rel: rel.endswith(".cache")) == (400, 1000, 1)
    assert tui_sizes.quick_size({"home": folders}, quick.rules(next(q for q in quick.QUICK if q.id == "models"), "u"),
                                "u") == 90


def test_files_lists_and_copy_gets_one_thing_out(sandbox, tmp_path, monkeypatch, capsys):
    home = tree(tmp_path / "point/u", {"Documents/letter.odt": 1200, "notes.txt": 5})
    calls = []
    monkeypatch.setattr(rootjob, "run", lambda job, request: calls.append(job) or {"path": str(home)})
    files_cmd.run_files(SimpleNamespace(point="001-2026-11-14-0900", folder=""), Events())
    assert "Documents/" in capsys.readouterr().out and calls == ["browse-open", "browse-close"]
    out = tmp_path / "out"
    out.mkdir()
    files_cmd.run_copy(SimpleNamespace(point="001-2026-11-14-0900", path="~/Documents/letter.odt", where=str(out)),
                       Events())
    assert (out / "letter.odt").stat().st_size == 1200
    try:
        files_cmd.run_copy(SimpleNamespace(point="001-2026-11-14-0900", path="Documents/letter.odt",
                                           where=str(out)), Events())
        raise AssertionError("copied over a file that was already there")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "exists"
    try:
        files_cmd.run_files(SimpleNamespace(point="001-2026-11-14-0900", folder="../../etc"), Events())
        raise AssertionError("listed outside the restore point")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "bad-path"
