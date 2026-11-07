"""The fake server: the real gatekeeper, in test mode, in a temporary folder.

Like systemd's socket (Accept=yes), every connection to the gatekeeper's
socket starts its own `gate serve` process with the connection as its input.
Requests go through the real `gate client` relay, as an SSH key's forced
command would run it. Only the encrypted box is pretend (fakehost.py).
"""

import base64
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "server" / "gate"
PYTHON = os.environ.get("OMABACKUPS_GATE_PYTHON", sys.executable)


def make_pubkey(n: int) -> str:
    blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes([n]) * 32
    return "ssh-ed25519 " + base64.b64encode(blob).decode()


class FakeServer:
    def __init__(self, root: Path):
        self.root = root
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        self.env["OMABACKUPS_GATE_ROOT"] = str(root)
        self.sock_path = root / "run" / "omabackups-gate" / "gate.sock"
        self.sock_path.parent.mkdir(parents=True)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.sock_path))
        self.listener.listen(16)
        self.procs = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            proc = subprocess.Popen([PYTHON, str(GATE), "serve"], stdin=conn.fileno(),
                                    env=self.env, stdout=subprocess.DEVNULL)
            conn.close()
            self.procs.append(proc)

    def close(self):
        self.listener.close()
        for proc in self.procs:
            proc.wait(timeout=30)

    # --- what the tests use --------------------------------------------------

    def gate(self, *args: str, input: bytes = b"", env: dict | None = None):
        return subprocess.run([PYTHON, str(GATE), *args], input=input, capture_output=True,
                              env={**self.env, **(env or {})}, timeout=60)

    def call(self, kid: str, command: str, input: bytes = b""):
        """One request, as the SSH key `kid` would send it. Returns (code, answer, error)."""
        done = self.gate("client", kid, input=input, env={"SSH_ORIGINAL_COMMAND": command})
        answer = json.loads(done.stdout) if done.stdout.strip() else None
        return done.returncode, answer, done.stderr.decode()

    def ok(self, kid: str, command: str, input: bytes = b"") -> dict:
        code, answer, error = self.call(kid, command, input)
        assert code == 0, error
        return answer

    def init(self) -> Path:
        store = self.root / "data" / "store"
        assert self.gate("admin", "init", str(store)).returncode == 0
        return store

    def add_computer(self, n: int, system: str | None = None) -> str:
        system = system or f"{n:032x}"
        done = self.gate("admin", "add-computer", system, f"computer {n}",
                         input=make_pubkey(n).encode())
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)["key"]

    def create(self, kid: str, password: str = "correct horse", key: bytes = b"K" * 64,
               size: int = 2 << 30) -> str:
        secrets = json.dumps({"password": password, "key": base64.b64encode(key).decode()})
        return self.ok(kid, f"create {size}", secrets.encode())["id"]
