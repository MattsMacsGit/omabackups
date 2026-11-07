"""The gatekeeper's read-only SFTP server for Browse (D37): it reads and lists
inside one restore point, and nothing else."""

import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "server" / "gate"))
import sftp  # noqa: E402


def s(text: str) -> bytes:
    data = text.encode()
    return struct.pack(">I", len(data)) + data


class Client:
    def __init__(self, root):
        self.server = sftp.Server(str(root))
        self.rid = 0

    def ask(self, kind: int, payload: bytes = b"") -> tuple[int, sftp.Reader]:
        self.rid += 1
        reply = self.server.answer(kind, struct.pack(">I", self.rid) + payload)
        r = sftp.Reader(reply[1:])
        assert r.u32() == self.rid
        return reply[0], r

    def status(self, kind: int, payload: bytes) -> int:
        got, r = self.ask(kind, payload)
        assert got == sftp.STATUS
        return r.u32()

    def read_file(self, path: str) -> bytes:
        got, r = self.ask(sftp.OPEN, s(path) + struct.pack(">II", sftp.F_READ, 0))
        assert got == sftp.HANDLE, (got, r.u32())
        handle = r.string()
        out = b""
        while True:
            got, r = self.ask(sftp.READ, struct.pack(">I", len(handle)) + handle
                              + struct.pack(">QI", len(out), 32768))
            if got == sftp.STATUS:
                assert r.u32() == sftp.EOF
                break
            out += r.string()
        self.ask(sftp.CLOSE, struct.pack(">I", len(handle)) + handle)
        return out

    def list(self, path: str) -> list[str]:
        got, r = self.ask(sftp.OPENDIR, s(path))
        assert got == sftp.HANDLE
        handle = r.string()
        names = []
        while True:
            got, r = self.ask(sftp.READDIR, struct.pack(">I", len(handle)) + handle)
            if got == sftp.STATUS:
                break
            for _ in range(r.u32()):
                names.append(r.text())
                r.text()
                flags = r.u32()
                assert flags & sftp.A_PERMISSIONS
                r.u64(), r.u32(), r.u32(), r.u32(), r.u32(), r.u32()
        return names


@pytest.fixture
def point(tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("not yours")
    root = tmp_path / "point"
    (root / "home/u/Documents").mkdir(parents=True)
    (root / "home/u/Documents/letter.txt").write_text("dear you")
    (root / "system/etc").mkdir(parents=True)
    (root / "system/etc/hostname").write_text("box")
    os.symlink("/system/etc/hostname", root / "home/u/abs-link")         # absolute: inside the jail
    os.symlink("../../../../outside.txt", root / "home/u/up-link")       # climbs: stops at the root
    os.symlink(str(secret), root / "home/u/real-abs")                    # a real path outside
    return root


def test_it_reads_and_lists_inside_the_point(point):
    c = Client(point)
    assert c.read_file("/home/u/Documents/letter.txt") == b"dear you"
    assert set(c.list("/home/u")) >= {"Documents", "abs-link", "up-link", ".", ".."}


def test_links_never_lead_outside_the_point(point):
    c = Client(point)
    assert c.read_file("/home/u/abs-link") == b"box"          # /system/... means the point's own
    for path in ("/home/u/up-link", "/home/u/real-abs", "/../outside.txt", "/../../../outside.txt"):
        got, r = c.ask(sftp.OPEN, s(path) + struct.pack(">II", sftp.F_READ, 0))
        assert got == sftp.STATUS and r.u32() == sftp.NO_SUCH_FILE, path


def test_readlink_shows_the_link_as_it_is(point):
    c = Client(point)
    got, r = c.ask(sftp.READLINK, s("/home/u/abs-link"))
    assert got == sftp.NAME and r.u32() == 1 and r.text() == "/system/etc/hostname"


def test_realpath_stays_inside(point):
    c = Client(point)
    got, r = c.ask(sftp.REALPATH, s("/../../home/./u/.."))
    assert got == sftp.NAME and r.u32() == 1 and r.text() == "/home"


def test_nothing_can_be_changed(point):
    c = Client(point)
    write = struct.pack(">II", 0x02 | 0x08, 0)       # write + create
    assert c.status(sftp.OPEN, s("/home/u/new.txt") + write) == sftp.PERMISSION_DENIED
    for kind in (13, 14, 15, 18, 9):                  # remove, mkdir, rmdir, rename, setstat
        assert c.status(kind, s("/home/u/Documents/letter.txt") + s("/x")) == sftp.PERMISSION_DENIED
    assert (point / "home/u/Documents/letter.txt").read_text() == "dear you"


def test_the_stream_speaks_packets(point):
    import io
    packet = struct.pack(">B", sftp.INIT) + struct.pack(">I", 3)
    out = io.BytesIO()
    sftp.serve(str(point), io.BytesIO(struct.pack(">I", len(packet)) + packet), out)
    reply = out.getvalue()
    assert struct.unpack(">IBI", reply[:9]) == (5, sftp.VERSION, 3)


def test_the_real_sftp_client_can_browse_and_copy_out(point, tmp_path):
    import shutil
    import subprocess
    if not shutil.which("sftp"):
        pytest.skip("no sftp client here")
    gate = Path(__file__).parent.parent / "server" / "gate"
    out = tmp_path / "copied.txt"
    batch = f"ls /home/u\nget /home/u/Documents/letter.txt {out}\nput {out} /home/u/x\n"
    done = subprocess.run(["sftp", "-b", "-", "-D", f"{sys.executable} {gate} sftp {point}"],
                          input=batch, capture_output=True, text=True, timeout=30)
    assert "Documents" in done.stdout
    assert out.read_text() == "dear you"
    assert not (point / "home/u/x").exists()          # put refused (batch stops there)
