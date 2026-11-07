"""The OmaBackups gatekeeper (BUILD 5.3). One file on the server (a zipapp).

  gate.pyz serve           the root side: one request on the socket (fd 0),
                           started per connection by omabackups-gate.socket
  gate.pyz client KEY      the forced command of every key: relays this SSH
                           login's request to the socket, nothing else
  gate.pyz sweep           from omabackups-gate-sweep.timer: lock quiet backups
  gate.pyz install ...     set up this server (as root, by `omabackups setup server`)
  gate.pyz admin ...       keys and the store (as root)
  gate.pyz version
"""

import json
import os
import shlex
import socket
import struct
import sys
import syslog

import admin
import conf
import verbs
import wire
from registry import Refused


def log(message: str) -> None:
    if conf.TEST:   # the tests must never write to the real system log
        return
    syslog.syslog(syslog.LOG_INFO, message)


def peer_allowed(sock: socket.socket) -> bool:
    """Only the gatekeeper account (or root) may talk to the socket."""
    creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", creds)
    if conf.TEST:
        return uid == os.geteuid()
    import pwd
    try:
        return uid in (0, pwd.getpwnam(conf.ACCOUNT).pw_uid)
    except KeyError:
        return uid == 0


def serve(sock: socket.socket) -> int:
    def answer(code: int, out: bytes = b"", err: str = "") -> int:
        try:
            if out:
                wire.send_frame(sock, wire.OUT, out)
            if err:
                wire.send_frame(sock, wire.ERR, f"omabackups-gate: {err}\n".encode())
            wire.send_frame(sock, wire.EXIT, struct.pack(">i", code))
        except OSError:
            pass
        return code

    if not peer_allowed(sock):
        return answer(1, err="not allowed")
    try:
        request, early = wire.read_request(sock)
        kid, words = str(request.get("key", "")), shlex.split(str(request.get("cmd", "")))
    except (EOFError, ValueError) as exc:
        return answer(2, err=f"bad request ({exc})")
    if not words or words[0] not in verbs.VERBS:
        return answer(2, err=f"unknown request: {words[0] if words else '(nothing)'}")

    buffered = [early]

    def read_input(limit: int) -> bytes:
        data = b"".join(buffered)
        buffered.clear()
        while len(data) <= limit:
            part = sock.recv(wire.CHUNK)
            if not part:
                break
            data += part
        return data[:limit + 1]

    verb = words[0]
    try:
        result = verbs.VERBS[verb](verbs.Call(kid, words[1:], read_input))
    except Refused as exc:
        log(f"refused {verb} for key {kid[:16]}: {exc}")
        return answer(1, err=str(exc))
    except Exception as exc:  # noqa: BLE001 - always answer, never hang the client
        log(f"error in {verb} for key {kid[:16]}: {exc!r}")
        return answer(1, err=f"{verb} failed on the server: {exc}")
    if verb not in ("version", "status", "points", "space", "hold"):
        log(f"{verb} done for key {kid[:16]}")
    return answer(0, out=(json.dumps(result, sort_keys=True) + "\n").encode())


def client(kid: str) -> int:
    command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(conf.SOCKET))
    except OSError as exc:
        sys.stderr.write(f"omabackups-gate: the gatekeeper service isn't running ({exc.strerror})\n")
        return 255
    return wire.relay(sock, kid, command)


def main(argv: list[str]) -> int:
    syslog.openlog("omabackups-gate")
    if argv[:1] == ["version"]:
        print(json.dumps({"gate": conf.VERSION, "contract": conf.CONTRACT}))
        return 0
    if argv[:1] == ["serve"]:
        return serve(socket.socket(fileno=os.dup(0)))
    if argv[:1] == ["client"] and len(argv) == 2:
        return client(argv[1])
    if argv[:1] == ["sweep"]:
        for bid in verbs.sweep():
            log(f"locked {bid[:12]}: nobody holding it, and quiet")
        return 0
    if argv[:1] == ["admin"]:
        return admin.main(argv[1:])
    if argv[:1] == ["install"]:
        import install
        return install.main(argv[1:])
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
