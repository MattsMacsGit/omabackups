"""Root job: save the skip list the picker made (D12/D13).

The list lives in /etc/omabackups/skips.json (root-owned: what the backup
reads). The next backup sees it changed and does a full check: newly
skipped things leave the working copy (older restore points keep them),
newly ticked ones are sent, or reused if the backup already has them (D25).
"""

import json

from omabackups.backup import skips
from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic

PARTS = ("system", "home", "boot")
MAX_RULES = 5000


def set_skips(request: dict) -> dict:
    given = request.get("skips")
    if not isinstance(given, dict) or not set(given) <= set(PARTS):
        raise OmaError("The skip list is damaged.", "Try again.", code="bad-request")
    clean = {"format": 2}
    for part, rules in given.items():
        if (not isinstance(rules, list) or len(rules) > MAX_RULES
                or not all(isinstance(r, str) and r.strip() and "\n" not in r and len(r) < 4096
                           for r in rules)):
            raise OmaError("The skip list is damaged.", "Try again.", part, code="bad-request")
        clean[part] = rules
    for part in PARTS:          # parts the picker didn't touch keep what they had
        clean.setdefault(part, skips.patterns_for(part))
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    write_atomic(paths.system_config_dir() / "skips.json",
                 (json.dumps(clean, indent=1) + "\n").encode(), 0o644)
    from omabackups.backup import run
    run.pause_automatic("the picker's choices changed")
    return {"saved": {p: len(clean[p]) for p in PARTS}}
