"""A read-only SFTP (version 3) server for one restore point (D37: Browse).

  gate.pyz sftp ROOT      speaks SFTP on stdin/stdout, inside ROOT only

Run by the `browse` verb; the computer mounts it with sshfs. It can read and
list, nothing else: every request that would change something is refused.
ROOT is the jail: paths are resolved as if ROOT were "/", symlinks included
(an absolute link starts again at ROOT; ".." stops at ROOT), so nothing
outside it can be named. A restore point is a read-only snapshot, so what was
checked can't change under us.
"""

import os
import stat
import struct
import sys

INIT, VERSION, OPEN, CLOSE, READ = 1, 2, 3, 4, 5
LSTAT, FSTAT, OPENDIR, READDIR, REALPATH, STAT, READLINK = 7, 8, 11, 12, 16, 17, 19
STATUS, HANDLE, DATA, NAME, ATTRS = 101, 102, 103, 104, 105
OK, EOF, NO_SUCH_FILE, PERMISSION_DENIED, FAILURE, BAD_MESSAGE, UNSUPPORTED = 0, 1, 2, 3, 4, 5, 8
F_READ = 0x01
A_SIZE, A_UIDGID, A_PERMISSIONS, A_TIME = 0x1, 0x2, 0x4, 0x8
MAX_PACKET = 256 * 1024
MAX_READ = 64 * 1024
MAX_HOPS = 40
MAX_HANDLES = 256


class Refusal(Exception):
    def __init__(self, code: int, text: str):
        super().__init__(text)
        self.code, self.text = code, text


def _parts(path: str) -> list[str]:
    return [p for p in path.split("/") if p not in ("", ".")]


class Jail:
    def __init__(self, root: str):
        self.root = os.path.realpath(root)

    def resolve(self, path: str, follow_last: bool = True) -> str:
        """The real path under ROOT for a client's path (chroot rules)."""
        todo, done, hops = _parts(path), [], 0
        while todo:
            name = todo.pop(0)
            if name == "..":
                if done:
                    done.pop()
                continue
            real = os.path.join(self.root, *done, name)
            try:
                st = os.lstat(real)
            except OSError:
                if todo:
                    raise Refusal(NO_SUCH_FILE, "no such file") from None
                done.append(name)     # the last part may be missing: callers see that
                continue
            if stat.S_ISLNK(st.st_mode) and (todo or follow_last):
                hops += 1
                if hops > MAX_HOPS:
                    raise Refusal(FAILURE, "too many links")
                target = os.readlink(real)
                if target.startswith("/"):
                    done = []
                todo = _parts(target) + todo
                continue
            done.append(name)
        return os.path.join(self.root, *done)

    def shown(self, path: str) -> str:
        """REALPATH: the client's path made absolute and tidy (inside the jail)."""
        out = []
        for name in _parts(path):
            if name == "..":
                if out:
                    out.pop()
            else:
                out.append(name)
        return "/" + "/".join(out)


def _string(data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + data


def attrs(st: os.stat_result) -> bytes:
    return struct.pack(">IQIIIII", A_SIZE | A_UIDGID | A_PERMISSIONS | A_TIME, st.st_size,
                       st.st_uid, st.st_gid, st.st_mode, int(st.st_atime), int(st.st_mtime))


def longname(name: str, st: os.stat_result) -> str:
    return f"{stat.filemode(st.st_mode)} 1 {st.st_uid} {st.st_gid} {st.st_size} Jan  1 00:00 {name}"


class Reader:
    def __init__(self, payload: bytes):
        self.data, self.at = payload, 0

    def u32(self) -> int:
        if self.at + 4 > len(self.data):
            raise Refusal(BAD_MESSAGE, "short message")
        (value,) = struct.unpack_from(">I", self.data, self.at)
        self.at += 4
        return value

    def u64(self) -> int:
        if self.at + 8 > len(self.data):
            raise Refusal(BAD_MESSAGE, "short message")
        (value,) = struct.unpack_from(">Q", self.data, self.at)
        self.at += 8
        return value

    def string(self) -> bytes:
        size = self.u32()
        if self.at + size > len(self.data):
            raise Refusal(BAD_MESSAGE, "short message")
        value = self.data[self.at:self.at + size]
        self.at += size
        return value

    def text(self) -> str:
        return self.string().decode("utf-8", "surrogateescape")


class Server:
    def __init__(self, root: str):
        self.jail = Jail(root)
        self.files: dict[bytes, int] = {}
        self.dirs: dict[bytes, list] = {}
        self.next = 0

    def _handle(self) -> bytes:
        if len(self.files) + len(self.dirs) >= MAX_HANDLES:
            raise Refusal(FAILURE, "too many open files")
        self.next += 1
        return str(self.next).encode()

    def status(self, rid: int, code: int, text: str = "") -> bytes:
        return struct.pack(">BII", STATUS, rid, code) + _string(text.encode()) + _string(b"")

    def answer(self, kind: int, payload: bytes) -> bytes:
        """One reply to one packet (type + payload, without the length)."""
        if kind == INIT:
            return struct.pack(">BI", VERSION, 3)
        r = Reader(payload)
        rid = r.u32()
        try:
            return self._reply(kind, rid, r)
        except Refusal as exc:
            return self.status(rid, exc.code, exc.text)
        except OSError as exc:
            code = NO_SUCH_FILE if exc.errno == 2 else PERMISSION_DENIED if exc.errno in (1, 13) else FAILURE
            return self.status(rid, code, exc.strerror or "failed")

    def _reply(self, kind: int, rid: int, r: Reader) -> bytes:
        if kind in (STAT, LSTAT):
            st = os.lstat(self.jail.resolve(r.text(), follow_last=kind == STAT))
            return struct.pack(">BI", ATTRS, rid) + attrs(st)
        if kind == REALPATH:
            path = self.jail.shown(r.text())
            st = os.lstat(self.jail.resolve(path))
            return (struct.pack(">BII", NAME, rid, 1) + _string(path.encode("utf-8", "surrogateescape"))
                    + _string(longname(path, st).encode("utf-8", "surrogateescape")) + attrs(st))
        if kind == READLINK:
            target = os.readlink(self.jail.resolve(r.text(), follow_last=False))
            return (struct.pack(">BII", NAME, rid, 1) + _string(target.encode("utf-8", "surrogateescape"))
                    + _string(b"") + struct.pack(">I", 0))
        if kind == OPEN:
            path, flags = r.text(), r.u32()
            if flags != F_READ:
                raise Refusal(PERMISSION_DENIED, "a restore point is read-only")
            fd = os.open(self.jail.resolve(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NOCTTY)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise Refusal(FAILURE, "not a file")
            handle = self._handle()
            self.files[handle] = fd
            return struct.pack(">BI", HANDLE, rid) + _string(handle)
        if kind == OPENDIR:
            path = self.jail.resolve(r.text())
            if not os.path.isdir(path) or os.path.islink(path):
                raise Refusal(NO_SUCH_FILE, "not a folder")
            handle = self._handle()
            self.dirs[handle] = [".", ".."] + sorted(os.listdir(path)) + [None]
            self.dirs[handle].insert(0, path)
            return struct.pack(">BI", HANDLE, rid) + _string(handle)
        if kind == READDIR:
            return self._readdir(rid, r.string())
        if kind == READ:
            handle, offset, size = r.string(), r.u64(), r.u32()
            if handle not in self.files:
                raise Refusal(FAILURE, "bad handle")
            data = os.pread(self.files[handle], min(size, MAX_READ), offset)
            if not data:
                raise Refusal(EOF, "end of file")
            return struct.pack(">BI", DATA, rid) + _string(data)
        if kind == FSTAT:
            handle = r.string()
            if handle not in self.files:
                raise Refusal(FAILURE, "bad handle")
            return struct.pack(">BI", ATTRS, rid) + attrs(os.fstat(self.files[handle]))
        if kind == CLOSE:
            handle = r.string()
            if handle in self.files:
                os.close(self.files.pop(handle))
            elif self.dirs.pop(handle, None) is None:
                raise Refusal(FAILURE, "bad handle")
            return self.status(rid, OK)
        if kind in (6, 9, 10, 13, 14, 15, 18, 20):      # write, setstat, remove, mkdir...
            raise Refusal(PERMISSION_DENIED, "a restore point is read-only")
        raise Refusal(UNSUPPORTED, "not supported")

    def _readdir(self, rid: int, handle: bytes) -> bytes:
        if handle not in self.dirs:
            raise Refusal(FAILURE, "bad handle")
        folder, names = self.dirs[handle][0], self.dirs[handle][1:]
        batch, out = [], b""
        while names and names[0] is not None and len(batch) < 100:
            name = names.pop(0)
            try:
                st = os.lstat(os.path.join(folder, name))
            except OSError:
                continue
            batch.append(name)
            raw = name.encode("utf-8", "surrogateescape")
            out += _string(raw) + _string(longname(name, st).encode("utf-8", "surrogateescape")) + attrs(st)
        self.dirs[handle] = [folder] + names
        if not batch:
            raise Refusal(EOF, "end of folder")
        return struct.pack(">BII", NAME, rid, len(batch)) + out


def _read_exactly(stream, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return data


def serve(root: str, stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    server = Server(root)
    try:
        while True:
            (size,) = struct.unpack(">I", _read_exactly(stdin, 4))
            if not 1 <= size <= MAX_PACKET:
                return 1
            packet = _read_exactly(stdin, size)
            reply = server.answer(packet[0], packet[1:])
            stdout.write(struct.pack(">I", len(reply)) + reply)
            stdout.flush()
    except (EOFError, BrokenPipeError):
        return 0
