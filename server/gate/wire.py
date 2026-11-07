"""How the relay and the gatekeeper talk over the socket.

Client -> gatekeeper: one JSON line {"key": <key id>, "cmd": <the request>},
then the raw input stream; end of input = the client shuts its side.
Gatekeeper -> client: frames of [kind: 1 byte][length: 4 bytes][data]:
  b"O" output, b"E" messages for stderr, b"X" the exit code (last frame).
Frames are needed because a socket has no exit code of its own.
"""

import json
import os
import socket
import struct
import sys
import threading

from conf import MAX_REQUEST

OUT, ERR, EXIT = b"O", b"E", b"X"
_HEAD = struct.Struct(">cI")
CHUNK = 1 << 16


def send_frame(sock: socket.socket, kind: bytes, data: bytes) -> None:
    sock.sendall(_HEAD.pack(kind, len(data)) + data)


def read_exactly(sock: socket.socket, n: int) -> bytes:
    parts = []
    while n:
        part = sock.recv(min(n, CHUNK))
        if not part:
            raise EOFError("connection closed mid-frame")
        parts.append(part)
        n -= len(part)
    return b"".join(parts)


def read_frame(sock: socket.socket) -> tuple[bytes, bytes] | None:
    head = sock.recv(_HEAD.size, socket.MSG_WAITALL)
    if not head:
        return None
    if len(head) < _HEAD.size:
        raise EOFError("connection closed mid-frame")
    kind, size = _HEAD.unpack(head)
    return kind, read_exactly(sock, size) if size else b""


def read_request(sock: socket.socket) -> tuple[dict, bytes]:
    """The first line, and any input bytes that arrived with it."""
    buf = b""
    while b"\n" not in buf:
        part = sock.recv(CHUNK)
        if not part:
            raise EOFError("no request")
        buf += part
        if len(buf) > MAX_REQUEST:
            raise ValueError("request too long")
    line, rest = buf.split(b"\n", 1)
    request = json.loads(line)
    if not isinstance(request, dict):
        raise ValueError("bad request")
    return request, rest


def relay(sock: socket.socket, key_id: str, command: str, stdin=None, stdout=None, stderr=None) -> int:
    """The client side: send the request and our input, play back the frames."""
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    stderr = stderr if stderr is not None else sys.stderr.buffer
    sock.sendall(json.dumps({"key": key_id, "cmd": command}).encode() + b"\n")
    # Whoever started us may have left our input/output non-blocking (rsync does):
    # then a big write fails instead of waiting. Make them wait.
    for f in (stdin, stdout, stderr):
        try:
            os.set_blocking(f.fileno(), True)
        except (OSError, ValueError, AttributeError):
            pass

    def pump_in():
        try:
            fd = stdin.fileno()
            while data := os.read(fd, CHUNK):
                sock.sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            try:
                sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    threading.Thread(target=pump_in, daemon=True).start()
    while frame := read_frame(sock):
        kind, data = frame
        if kind == OUT:
            stdout.write(data)
            stdout.flush()
        elif kind == ERR:
            stderr.write(data)
            stderr.flush()
        elif kind == EXIT:
            return struct.unpack(">i", data)[0]
    stderr.write(b"omabackups-gate: the connection ended early\n")
    return 255


class FdInput:
    """A plain file descriptor that reads like a socket (local mode: stdin)."""

    def __init__(self, fd: int):
        self.fd = fd

    def recv(self, n: int) -> bytes:
        return os.read(self.fd, n)


class Reader:
    """The caller's input: bytes that came with the request, then the socket."""

    def __init__(self, sock, early: bytes):
        self.sock = sock
        self.buf = early

    def read(self, n: int) -> bytes:
        """Up to n bytes; b"" once the caller has finished sending."""
        if not self.buf:
            return self.sock.recv(min(n, CHUNK))
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def exactly(self, n: int) -> bytes:
        parts = []
        while n:
            part = self.read(n)
            if not part:
                raise EOFError("input ended early")
            parts.append(part)
            n -= len(part)
        return b"".join(parts)

    def line(self, limit: int) -> bytes:
        out = b""
        while not out.endswith(b"\n"):
            part = self.read(1)
            if not part or len(out) > limit:
                break
            out += part
        return out

    def upto(self, limit: int) -> bytes:
        """Everything until the end, but never more than limit + 1 bytes."""
        data = b""
        while len(data) <= limit:
            part = self.read(CHUNK)
            if not part:
                break
            data += part
        return data[:limit + 1]

    def rest(self) -> bytes:
        """Hand back what's buffered (for a program that takes over the socket)."""
        out, self.buf = self.buf, b""
        return out
