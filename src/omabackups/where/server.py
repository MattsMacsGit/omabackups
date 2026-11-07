"""Talking to the backup server's gatekeeper (BUILD 5.3), as root.

Every answer is one JSON line; every refusal comes back as the gatekeeper's
own message, wrapped in a plain OmaError.
"""

import json
import os
import subprocess
import sys
import tempfile

from omabackups.core import log
from omabackups.core.errors import OmaError
from omabackups.where import ssh

GATE_CONTRACT = 1
GATE_NEEDED = 2     # the oldest gatekeeper this omabackups works with


class Gate:
    def __init__(self, address: str):
        self.address = address

    def _argv(self, command: str) -> tuple[list[str], dict | None]:
        fake = os.environ.get("OMABACKUPS_TEST_GATE")
        if fake and os.environ.get("OMABACKUPS_SYSROOT"):
            # Tests: the real gatekeeper in test mode, without SSH in between.
            gate_dir, key_id = fake.split(":")
            return ([sys.executable, gate_dir, "client", key_id],
                    dict(os.environ, SSH_ORIGINAL_COMMAND=command))
        return [*ssh.as_gatekeeper(self.address), command], None

    def call(self, verb: str, *args: str, data: bytes = b"") -> dict:
        command = " ".join([verb, *args])
        log.get("server").debug("gate: %s", verb)
        argv, env = self._argv(command)
        done = subprocess.run(argv, input=data, capture_output=True, env=env, timeout=600)
        return self._answer(verb, done)

    def call_streaming(self, verb: str, *args: str, feed) -> dict:
        """Like call(), with the input written by feed(pipe) as it goes (big data)."""
        argv, env = self._argv(" ".join([verb, *args]))
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err, env=env)
            try:
                feed(proc.stdin)
            except BrokenPipeError:
                pass   # the gatekeeper stopped early: its answer says why
            finally:
                proc.stdin.close()
            code = proc.wait()
            out.seek(0)
            err.seek(0)
            done = subprocess.CompletedProcess(argv, code, out.read(), err.read())
        return self._answer(verb, done)

    def _answer(self, verb: str, done) -> dict:
        error = done.stderr.decode("utf-8", "replace").strip()
        if done.returncode == 255 and not error.startswith("omabackups-gate:"):
            raise OmaError(
                "Your backup server can't be reached.",
                "Check that it's switched on and on the network, then try again.",
                error or "ssh exit 255", code="unreachable")
        if done.returncode != 0:
            message = error.removeprefix("omabackups-gate:").strip() or f"exit {done.returncode}"
            raise OmaError(f"The backup server said no: {message}.",
                           "If this doesn't explain itself, report it with the details.",
                           f"{verb}: {error}", code="gate-refused")
        try:
            return json.loads(done.stdout)
        except ValueError:
            raise OmaError("The backup server gave an answer OmaBackups can't read.",
                           "Run setup server again to update OmaBackups on the server.",
                           done.stdout[:500].decode("utf-8", "replace"), code="gate-garbled") from None

    def check_version(self) -> dict:
        answer = self.call("version")
        if answer.get("contract") != GATE_CONTRACT or answer.get("gate", 0) < GATE_NEEDED:
            raise OmaError("OmaBackups on your backup server needs updating.",
                           "Run: omabackups setup server --update (it asks for your login on "
                           "the server and its sudo password, once each). Your backup is kept.",
                           json.dumps(answer), code="gate-version")
        return answer
