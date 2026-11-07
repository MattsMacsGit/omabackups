"""The gatekeeper file that `setup server` copies to the server.

Installed by the package at /usr/share/omabackups/gate.pyz. Run from the
source tree (tests, development), it is packed on the spot from server/gate.
"""

import hashlib
import zipapp
from pathlib import Path

from omabackups.core import paths
from omabackups.core.errors import OmaError

_SOURCE = Path(__file__).resolve().parents[3] / "server" / "gate"


def gate_file() -> Path:
    installed = paths.gate_bundle()
    if installed.is_file():
        return installed
    if (_SOURCE / "__main__.py").is_file():
        out = paths.cache_dir() / "gate.pyz"
        out.parent.mkdir(parents=True, exist_ok=True)
        zipapp.create_archive(_SOURCE, out, interpreter="/usr/bin/env python3",
                              filter=lambda p: "__pycache__" not in p.parts)
        return out
    raise OmaError("The gatekeeper file is missing from the omabackups package.",
                   "Reinstall the omabackups package, then try again.",
                   str(installed), code="no-gate")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
