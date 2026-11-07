"""Talking to the backup server's gatekeeper (BUILD 5.3), as root.

Every answer is one JSON line; every refusal comes back as the gatekeeper's
own message, wrapped in a plain OmaError.
"""

import json
import os
import subprocess
import sys

from omabackups.core import log
from omabackups.core.errors import OmaError
from omabackups.where import ssh

GATE_CONTRACT = 1


class Gate:
    def __init__(self, address: str):
        self.address = address

    def _run(self, command: str, data: bytes) -> subprocess.CompletedProcess:
        fake = os.environ.get("OMABACKUPS_TEST_GATE")
        if fake and os.environ.get("OMABACKUPS_SYSROOT"):
            # Tests: the real gatekeeper in test mode, without SSH in between.
            gate_dir, key_id = fake.split(":")
            env = dict(os.environ, SSH_ORIGINAL_COMMAND=command)
            return subprocess.run([sys.executable, gate_dir, "client", key_id],
                                  input=data, capture_output=True, env=env, timeout=600)
        return subprocess.run([*ssh.as_gatekeeper(self.address), command],
                              input=data, capture_output=True, timeout=600)

    def call(self, verb: str, *args: str, data: bytes = b"") -> dict:
        command = " ".join([verb, *args])
        log.get("server").debug("gate: %s", verb)
        done = self._run(command, data)
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
        if answer.get("contract") != GATE_CONTRACT:
            raise OmaError("OmaBackups on your backup server is a different version.",
                           "Run setup server again to update it.",
                           json.dumps(answer), code="gate-version")
        return answer
