"""Checking what a computer asks rsync's server side to do (like rrsync).

The computer's rsync sends its server-side arguments; only a short list of
known-safe ones is accepted, and the destination is always replaced by the
gatekeeper's own path. Options that name other paths on the server
(--log-file, --link-dest, --temp-dir, --backup-dir...) are never allowed.
"""

import re

from registry import Refused

# One cluster of short options, ending in rsync's protocol letters ("e.xxx").
_SHORT = re.compile(r"^-[lHogDtpAXrRSzcvnxIW]*e\.[A-Za-z]*$")
_LONG = {
    "--delete", "--delete-during", "--delete-after", "--delete-delay", "--delete-excluded",
    "--numeric-ids", "--inplace", "--stats", "--ignore-errors", "--force",
    "--compress-choice=zstd", "--size-only", "--checksum-choice=xxh128",
}
PARTIAL_DIR = ".rsync-partial"


def check(args: list[str], sender: bool) -> list[str]:
    """The checked server options (without the trailing ". DEST")."""
    if len(args) < 4 or args[0] != "--server" or args[-2] != ".":
        raise Refused("that isn't an rsync request")
    body = args[1:-2]
    if sender:
        if not body or body[0] != "--sender":
            raise Refused("a fetch must be rsync's sending side")
        body = body[1:]
    elif "--sender" in body:
        raise Refused("a send can't read from the server")
    out = ["--server"] + (["--sender"] if sender else [])
    i = 0
    while i < len(body):
        arg = body[i]
        if _SHORT.match(arg) or arg in _LONG:
            out.append(arg)
        elif arg == "--partial-dir" and i + 1 < len(body) and body[i + 1] == PARTIAL_DIR:
            out += [arg, PARTIAL_DIR]
            i += 1
        else:
            raise Refused(f"rsync option not allowed here: {arg[:40]}")
        i += 1
    if not any(_SHORT.match(a) for a in out):
        raise Refused("that isn't an rsync request")
    return out
