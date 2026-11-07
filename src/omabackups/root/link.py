"""`omabackups link`, run as root through pkexec, once at setup (D27).

pkexec has just asked for this computer's password. This:
- records which user OmaBackups belongs to (/etc/omabackups/user.json);
- writes the polkit rule that lets only that user start and stop
  OmaBackups' own root jobs (5.2). It names the user directly: a group
  would only count after the user logs in again;
- makes the root-only keys and prints only the public half.
"""

import json
import os
import pwd
import re

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.events import Events
from omabackups.core.state import write_atomic
from omabackups.root import keys


def caller() -> pwd.struct_passwd:
    uid = os.environ.get("PKEXEC_UID", "")
    if not uid.isdigit() or int(uid) == 0:
        raise OmaError("Run this from your own user, not as root.",
                       "Use 'omabackups setup server' (it asks for your password itself).",
                       code="not-linked")
    return pwd.getpwuid(int(uid))


RULE = """// OmaBackups (BUILD 5.2, D27): written by `omabackups link`.
// Only USER, in an active local session, may start and stop OmaBackups' own
// root jobs without a password. Nothing else.
polkit.addRule(function (action, subject) {
  if (action.id !== "org.freedesktop.systemd1.manage-units") return;
  if (subject.user !== "USER" || !subject.local || !subject.active) return;
  var verb = action.lookup("verb");
  if (verb !== "start" && verb !== "stop") return;
  var unit = action.lookup("unit");
  if (/^omabackups-root@[a-z][a-z-]{0,40}\\.service$/.test(unit)) return polkit.Result.YES;
});
"""
USER_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def link(user: pwd.struct_passwd) -> dict:
    if not USER_NAME.match(user.pw_name):
        raise OmaError(f"OmaBackups can't work with the user name '{user.pw_name}'.",
                       "Use a user whose name is lower-case letters, digits, - or _.",
                       code="bad-user")
    pub = keys.ensure()
    rule = paths.polkit_rule_file()
    rule.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(rule, RULE.replace("USER", user.pw_name).encode(), 0o644)
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    write_atomic(paths.linked_user_file(),
                 (json.dumps({"user": user.pw_name, "uid": user.pw_uid}) + "\n").encode(), 0o644)
    return {"user": user.pw_name, "public_key": pub}


def run(args, events: Events) -> int:
    """`omabackups link` (as root, through pkexec). Errors reach cli.py."""
    result = link(caller())
    events.result(result, f"Linked {result['user']} to OmaBackups.")
    return 0
