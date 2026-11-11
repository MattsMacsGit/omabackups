"""Never send the same data twice (D25): what the server holds already is
reused, not sent: a folder no longer skipped, a file brought back from a
restore point, and after a user rename, under the name it had before."""

import json

import pytest  # noqa: F401
from test_run import FAKE_SSH, latest, same, world  # noqa: F401  (world: the fixture)

from omabackups.backup import run
from omabackups.core import paths


def spy_reuse(monkeypatch):
    answers = []
    real = run.reuse.ask

    def spy(*args):
        answer = real(*args)
        answers.append(answer)
        return answer
    monkeypatch.setattr(run.reuse, "ask", spy)
    return answers

def test_an_unskipped_folder_is_reused_not_sent(world, monkeypatch):
    srv, kid, bid, src, box = world
    (src.root / "home/u/Videos").mkdir()
    (src.root / "home/u/Videos/film.mkv").write_bytes(b"F" * 50_000)
    names = iter(f"001-2099-01-0{i}-0000" for i in range(1, 9))
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    run.backup(source=src)                                       # Videos backed up
    skips_file = paths.system_config_dir() / "skips.json"
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    skips_file.write_text(json.dumps({"home": ["Videos"]}))
    run.backup(source=src)                                       # skipped: leaves the working copy
    assert not (box / "current/001/home/u/Videos").exists()
    skips_file.write_text(json.dumps({"home": []}))
    answers = spy_reuse(monkeypatch)
    run.backup(source=src)                                       # un-skipped
    assert any(a["dirs"] == 1 for a in answers)
    same(latest(box), src)

def test_a_file_brought_back_from_a_restore_point_is_reused(world, monkeypatch):
    import shutil
    srv, kid, bid, src, box = world
    (src.root / "home/u/manual.pdf").write_bytes(b"P" * 40_000)
    names = iter(f"001-2099-01-0{i}-0000" for i in range(1, 9))
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    run.backup(source=src)
    kept = latest(box) / "home/u/manual.pdf"
    (src.root / "home/u/manual.pdf").unlink()
    run.backup(source=src)                                       # deleted
    shutil.copy2(kept, src.root / "home/u/manual.pdf")           # Restore my files keeps the date
    answers = spy_reuse(monkeypatch)
    result = run.backup(source=src)
    assert any(a["files"] == 1 and a["bytes"] == 40_000 for a in answers)
    assert result["how"]["home"].startswith("changes (")
    same(latest(box), src)

def test_an_unskipped_single_file_is_reused_not_sent(world, monkeypatch):
    srv, kid, bid, src, box = world
    (src.root / "home/u/big.iso").write_bytes(b"I" * 60_000)
    names = iter(f"001-2099-01-0{i}-0000" for i in range(1, 9))
    monkeypatch.setattr(run, "point_name", lambda line, latest: next(names))
    run.backup(source=src)
    skips_file = paths.system_config_dir() / "skips.json"
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    skips_file.write_text(json.dumps({"home": ["/u/big.iso"]}))
    run.backup(source=src)
    assert not (box / "current/001/home/u/big.iso").exists()
    skips_file.write_text(json.dumps({"home": []}))
    answers = spy_reuse(monkeypatch)
    run.backup(source=src)
    assert any(a["files"] == 1 and a["bytes"] == 60_000 for a in answers)
    same(latest(box), src)

def test_new_files_name_their_old_place_after_a_user_rename(tmp_path):
    """Stage 10: after a Migrate from another user name, reuse is told where
    the server may hold each file (the old name), home only."""
    from omabackups.backup import changes, reuse
    (tmp_path / "newu/Documents").mkdir(parents=True)
    (tmp_path / "newu/Documents/a.txt").write_text("a")
    plan = changes.Plan(files=["newu/Documents/a.txt"], fresh=["newu/Documents/a.txt"])
    entry = reuse.fresh_files(plan, str(tmp_path), ("newu", "oldu"))[0]
    assert entry[0] == "newu/Documents/a.txt" and entry[3] == "oldu/Documents/a.txt"
    assert len(reuse.fresh_files(plan, str(tmp_path))[0]) == 3
    assert run.renamed_home({"from_user": "oldu"}, "system") is None
