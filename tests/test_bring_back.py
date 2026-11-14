"""D52: Choose what comes back, the picker the other way round: the restore
point's home folder, a tick brings it back, colours say what's here."""

from pathlib import Path

from omabackups.core import rootjob
from omabackups.restore import files
from omabackups.tui.bring_back import BringBack, BringBackMode
from omabackups.tui.pick_model import Node


def _world(tmp_path):
    point, here = tmp_path / "point" / "home", tmp_path / "here"
    for rel, size in {"u/Documents/a.txt": 100, "u/Music/song.mp3": 3000, "u/Videos/film.mkv": 9000}.items():
        (point / rel).parent.mkdir(parents=True, exist_ok=True)
        (point / rel).write_bytes(b"x" * size)
    (here / "Documents").mkdir(parents=True)
    (here / "Documents/a.txt").write_bytes(b"x" * 100)
    return BringBack("u", point, here), point, here


def test_the_same_rows_the_other_way_round(tmp_path):
    m, point, here = _world(tmp_path)
    m.measure(m.home())
    assert [n.name for n in m.listing(m.home())] == ["Videos", "Music", "Documents"]
    assert m.listing(m.quick())[-1].name == "Your files"          # opens on Quick skips
    docs, music = Node("home", "u/Documents", "Documents", True), Node("home", "u/Music", "Music", True)
    assert m.colour(docs) == "green" and "already here" in m.explain(docs)
    assert m.colour(music) == "blue" and m.explain(music) == "Music: comes back."
    m.toggle(music)
    assert m.colour(music) == "grey" and m.explain(music) == "Music: stays in your backup. Space brings it back."
    m.measure(m.home())
    assert m.total() == 100 + 9000                        # what comes back
    assert m.bottom()[0].startswith("Bringing back 9.1 KB · this computer has ")


def test_what_stays_is_left_out_of_restore_my_files(tmp_path, monkeypatch):
    m, point, here = _world(tmp_path)
    m.toggle(Node("home", "u/Videos", "Videos", True))
    assert m.leave_out() == ["/Videos"]                   # relative to the home folder
    calls = []
    monkeypatch.setattr(rootjob, "run", lambda job, request: calls.append((job, request)) or {})
    monkeypatch.setattr("omabackups.tui.bring_back.state.write", lambda *a: None)
    assert BringBackMode("001-2026-11-12-1955", {"point": "001-2026-11-12-1955"}).save(m) is None
    assert calls[-1] == ("restore-files-start", {"point": "001-2026-11-12-1955", "leave_out": ["/Videos"],
                                                 "leave_out_system": []})


def test_restore_my_files_leaves_out_what_stays(tmp_path):
    class Gate:
        def rsh(self):
            return "ssh"

        def rsync_target(self):
            return "server"
    command = files.command(Gate(), "b", "001-2026-11-12-1955", "u", tmp_path, leave_out=["/Videos", ".cache"])
    assert "--exclude=/Videos" in command and "--exclude=.cache" in command
    assert files.clean_leave_out(["/Videos", "--rsync-path=x", "/a/../b", "ok\nno", 7, "!/Music/keep"]) \
        == ["/Videos", "!/Music/keep"]
