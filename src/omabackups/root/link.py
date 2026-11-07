"""`omabackups link`, run as root through pkexec, once at setup (D27).

pkexec has just asked for this computer's password. This:
- records which user OmaBackups belongs to (/etc/omabackups/user.json);
- puts that user in the `omabackups` group, which the package's fixed polkit
  rule lets start and stop OmaBackups' own units (5.2);
- makes the root-only keys and prints only the public half.
"""

import json
import os
import pwd
import subprocess

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


def link(user: pwd.struct_passwd) -> dict:
    if not os.environ.get("OMABACKUPS_SYSROOT"):   # tests can't change groups
        _join_group(user)
    pub = keys.ensure()
    paths.system_config_dir().mkdir(parents=True, exist_ok=True)
    write_atomic(paths.linked_user_file(),
                 (json.dumps({"user": user.pw_name, "uid": user.pw_uid}) + "\n").encode(), 0o644)
    return {"user": user.pw_name, "public_key": pub}


def _join_group(user: pwd.struct_passwd) -> None:
    if subprocess.run(["getent", "group", paths.GROUP], capture_output=True).returncode != 0:
        raise OmaError("The omabackups group is missing.",
                       "Reinstall the omabackups package, then try again.", code="no-group")
    done = subprocess.run(["gpasswd", "-a", user.pw_name, paths.GROUP], capture_output=True, text=True)
    if done.returncode != 0:
        raise OmaError(f"Couldn't add {user.pw_name} to the omabackups group.",
                       "Try again. If it keeps failing, report it with the details.",
                       done.stderr.strip(), code="link-failed")


def run(args, events: Events) -> int:
    """`omabackups link` (as root, through pkexec). Errors reach cli.py."""
    result = link(caller())
    events.result(result, f"Linked {result['user']} to OmaBackups.")
    return 0
