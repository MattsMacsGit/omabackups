"""A migrated computer's first backup takes the backup over (D22)."""

import json
import time

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic


def handover(gate, server: dict, user: str, logger) -> str:
    """A new line starts from the restore point Migrate came from (only
    changes are stored); the old one is read-only now, and that point is the
    Return point. Recorded only once the server said yes. `user`: this
    computer's user. Returns the new line."""
    point = server.get("from_point")
    if not point:
        raise OmaError("Migrate isn't finished on this computer yet.",
                       "Finish it first (the panel shows where it's up to).", code="migrate-unfinished")
    answer = gate.call("handover", server["backup"], point)
    # A new user name (testrig01 -> testrig02): the new line's copy of the home
    # folder takes this user's name, so only real changes are sent (stage 8:
    # 1.2 GB went again without this).
    old = server.get("from_user", "")
    if old and user and old != user:
        gate.call("apply", server["backup"], answer["line"], "home",
                  data=json.dumps([["rename", old, user]]).encode())
        logger.info("handover: the home folder %s is %s now", old, user)
    server = {**server, "line": answer["line"], "migrating": False,
              "return_point": answer["return_point"], "handed_over": int(time.time())}
    write_atomic(paths.server_file(), (json.dumps(server, indent=2) + "\n").encode(), 0o644)
    logger.info("handover: this computer owns the backup now, line %s from %s", answer["line"], point)
    return answer["line"]
