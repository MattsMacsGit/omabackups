"""Work inside a user's home folder, as that user (D59).

A root job never opens files in a user's home itself: the user can put a
symlink anywhere in there, and root would follow it to any file on the
computer. The step runs in a separate process with the user's own uid, gid
and groups (nothing of root's is kept), so it reaches only what the user
can. Its arguments go in as JSON on stdin; its answer comes back as JSON in
a private file root opened and handed to it (stdout stays unused: only
events print there).

Only the steps named in TASKS can be run this way.
"""

import importlib
import json
import os
import pwd
import sys
from pathlib import Path

from omabackups.core.errors import OmaError

TASKS = {
    "keep-first": "omabackups.migrate.home:keep_first",
    "merge": "omabackups.migrate.home:merge",
    "theme": "omabackups.migrate.home:theme",
    "rename": "omabackups.migrate.home:rename",
    "rename-later": "omabackups.migrate.home:rename_later",
    "missing": "omabackups.migrate.home:missing",
    "kept": "omabackups.migrate.home:kept",
    "histories": "omabackups.migrate.home:histories",
}


def dropping() -> bool:
    """Root drops to the user; anyone else already is that user (tests)."""
    return os.geteuid() == 0


def ids(user: str) -> tuple[int, int] | None:
    """The user's uid and gid when root has to hand things over, else None."""
    if not dropping():
        return None
    entry = pwd.getpwnam(user)
    return entry.pw_uid, entry.pw_gid


def give(path, user: str) -> None:
    """A folder root just made, handed to the user (before anything is in it)."""
    if (who := ids(user)) is not None:
        os.chown(path, *who)


def run(user: str | None, task: str, args: dict):
    """TASKS[task](**args), in its own process as `user`; its JSON answer."""
    import subprocess
    import tempfile
    if task not in TASKS:
        raise OmaError(f"There is no home step called '{task}'.", code="bad-job")
    # The same code as this process (its own folder first: -I ignores PYTHONPATH).
    here = str(Path(__file__).resolve().parents[2])
    command = [sys.executable, "-I", "-c",
               f"import sys; sys.path.insert(0, {here!r}); from omabackups.core.asuser import main; main()",
               task]
    extra, env = {}, dict(os.environ)
    if dropping():
        entry = pwd.getpwnam(str(user))
        extra = {"user": entry.pw_uid, "group": entry.pw_gid,
                 "extra_groups": os.getgrouplist(entry.pw_name, entry.pw_gid)}
        env = {"PATH": "/usr/bin", "HOME": entry.pw_dir, "USER": entry.pw_name,
               "LOGNAME": entry.pw_name, "LANG": os.environ.get("LANG", "C.UTF-8")}
    with tempfile.TemporaryFile() as answer:
        done = subprocess.run([*command, str(answer.fileno())], input=json.dumps(args).encode(),
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              pass_fds=(answer.fileno(),), env=env, cwd="/", **extra)
        if done.returncode != 0:
            raise OmaError("A step in your home folder didn't finish.",
                           "Run it again. If it stops here again, copy the details into an issue.",
                           done.stderr.decode("utf-8", "replace")[-2000:], code="home-step")
        answer.seek(0)
        return json.loads(answer.read())


def main() -> None:
    if os.geteuid() == 0:
        sys.exit("a home step never runs as root")
    module, name = TASKS[sys.argv[1]].split(":")
    result = getattr(importlib.import_module(module), name)(**json.loads(sys.stdin.read()))
    with os.fdopen(int(sys.argv[2]), "w") as answer:
        json.dump(result, answer)


if __name__ == "__main__":
    main()
