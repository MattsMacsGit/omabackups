"""Running a data program (rsync's server side) for one request.

The caller's input flows into the program; its output and messages flow back
as frames; its exit code ends the conversation. Used by the data verbs.
"""

import struct
import subprocess
import threading

import wire


class Stream:
    """What a data verb hands back: the program to run, already checked."""

    def __init__(self, command: list[str], cwd: str, on_done=None):
        self.command = command
        self.cwd = cwd
        self.on_done = on_done   # called with the exit code, before answering


def run(stream: Stream, sock, early: bytes) -> int:
    proc = subprocess.Popen(stream.command, cwd=stream.cwd, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sending = threading.Lock()

    def send(kind: bytes, data: bytes) -> None:
        with sending:
            wire.send_frame(sock, kind, data)

    def feed():
        try:
            if early:   # bytes that came along with the request: pass them on now
                proc.stdin.write(early)
                proc.stdin.flush()
            while data := sock.recv(wire.CHUNK):
                proc.stdin.write(data)
                proc.stdin.flush()
        except (OSError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    def messages():
        for line in proc.stderr:
            try:
                send(wire.ERR, line)
            except OSError:
                return

    feeder = threading.Thread(target=feed, daemon=True)
    talker = threading.Thread(target=messages, daemon=True)
    feeder.start()
    talker.start()
    try:
        while data := proc.stdout.read1(wire.CHUNK):
            send(wire.OUT, data)
    except OSError:
        proc.kill()
    code = proc.wait()
    talker.join(timeout=10)
    if stream.on_done:
        code = stream.on_done(code) or code
    try:
        send(wire.EXIT, struct.pack(">i", code))
    except OSError:
        pass
    return code
