"""The OmaBackups gatekeeper (BUILD 5.3). One file on the server (a zipapp).

  gate.pyz serve           the root side: one request on the socket (fd 0),
                           started per connection by omabackups-gate.socket
  gate.pyz client KEY      the forced command of every key: relays this SSH
                           login's request to the socket, nothing else
  gate.pyz sweep           from omabackups-gate-sweep.timer: lock quiet backups
  gate.pyz install ...     set up this server (as root, by `omabackups setup server`)
  gate.pyz admin ...       keys and the store (as root)
  gate.pyz sftp ROOT       read-only SFTP inside one restore point (the browse verb)
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
import stream
import verbs
import verbs_data
import verbs_health
import verbs_migrate
import verbs_remove
import wire
from registry import Refused

VERBS = {**verbs.VERBS, **verbs_data.VERBS, **verbs_health.VERBS, **verbs_migrate.VERBS, **verbs_remove.VERBS}


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
    if not words or words[0] not in VERBS:
        return answer(2, err=f"unknown request: {words[0] if words else '(nothing)'}")

    reader = wire.Reader(sock, early)
    verb = words[0]
    try:
        result = VERBS[verb](verbs.Call(kid, words[1:], reader))
    except Refused as exc:
        log(f"refused {verb} for key {kid[:16]}: {exc}")
        return answer(1, err=str(exc))
    except Exception as exc:  # noqa: BLE001 - always answer, never hang the client
        log(f"error in {verb} for key {kid[:16]}: {exc!r}")
        return answer(1, err=f"{verb} failed on the server: {exc}")
    if isinstance(result, stream.Stream):
        code = stream.run(result, sock, reader.rest())
        log(f"{verb} {' '.join(words[1:4])} ended with {code} for key {kid[:16]}")
        return code
    if verb not in ("version", "status", "points", "space", "hold"):
        log(f"{verb} done for key {kid[:16]}")
    return answer(0, out=(json.dumps(result, sort_keys=True) + "\n").encode())


def direct(kid: str) -> int:
    """Local mode (a backup disk on this computer): run one request straight
    from SSH_ORIGINAL_COMMAND, as root, on stdin/stdout. Never over SSH."""
    if not conf.LOCAL or (os.geteuid() != 0 and not conf.TEST):
        sys.stderr.write("omabackups-gate: direct is for a backup disk on this computer only\n")
        return 1
    words = shlex.split(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    if not words or words[0] not in VERBS:
        sys.stderr.write(f"omabackups-gate: unknown request: {words[0] if words else '(nothing)'}\n")
        return 2
    try:
        result = VERBS[words[0]](verbs.Call(kid, words[1:], wire.Reader(wire.FdInput(0), b"")))
    except Refused as exc:
        sys.stderr.write(f"omabackups-gate: {exc}\n")
        return 1
    if isinstance(result, stream.Stream):
        os.chdir(result.cwd)
        os.execvp(result.command[0], result.command)   # rsync takes over stdin/stdout
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


def direct_rsh(kid: str, args: list[str]) -> int:
    """Local mode, as rsync's -e program: [-l USER] HOST <request words...>."""
    if args[:1] == ["-l"]:
        args = args[2:]
    os.environ["SSH_ORIGINAL_COMMAND"] = " ".join(args[1:])
    return direct(kid)


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
    if argv[:1] == ["direct"] and len(argv) == 2:
        return direct(argv[1])
    if argv[:1] == ["direct-rsh"] and len(argv) >= 3:
        return direct_rsh(argv[1], argv[2:])
    if argv[:1] == ["sftp"] and len(argv) == 2:     # run by the browse verb (D37)
        import sftp
        return sftp.serve(argv[1])
    if argv[:1] == ["sizes"] and len(argv) == 3:     # started by the snapshot verb, as root
        import sizes
        from host import host, mountpoint
        try:
            if host().is_mounted(argv[1]):
                sizes.build(mountpoint(argv[1]), argv[2])
        finally:
            sizes.running_file(argv[1]).unlink(missing_ok=True)
        return 0
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
