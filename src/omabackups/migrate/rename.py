"""The old user name in the settings that came over (D41).

Only when the user name changed: in the settings Migrate just brought back,
`/home/<old>` becomes `/home/<new>`, so a setting that names a folder (git's
GitHub login helper, a download folder, a link into ~/.local) points at this
computer's home. The person had the backup's password: it's their setup,
only the name changed.

Small text files only (no NUL byte, 1 MB at most), and links. Owner and
permissions are kept. Caches are skipped.

Apps that sync folders (Nextcloud...) are left for later: pointed at folders
that aren't back yet, they'd start again from scratch. Their settings are
fixed once Restore my files has brought the folders back (later(), 1.x test
5 Nov). The app is stopped first: it rewrites its settings when it quits.
"""

import os
import re
from pathlib import Path

LIMIT = 1_000_000
# Sync apps: their settings folder -> (name, process).
SYNC_APPS = {".config/Nextcloud": ("Nextcloud", "nextcloud"),
             ".config/ownCloud": ("ownCloud", "owncloud"),
             ".config/syncthing": ("Syncthing", "syncthing"),
             ".local/state/syncthing": ("Syncthing", "syncthing")}


def sync_app(rel: str) -> tuple[str, str] | None:
    for folder, app in SYNC_APPS.items():
        if rel == folder or rel.startswith(folder + "/"):
            return app
    return None
SKIP_DIRS = {"Cache", "Code Cache", "GPUCache", "Service Worker", "IndexedDB", "blob_storage",
             "Crashpad", "ShaderCache", "GrShaderCache", "DawnCache", "DawnGraphiteCache", ".git",
             "node_modules", "__pycache__"}


def pattern(old_home: str) -> re.Pattern:
    # The old home folder, then the end of the path: "/", a quote, a space, ":"...
    return re.compile(re.escape(old_home.encode()) + rb"(?=[/\"'\s:;,=)\]}]|$)", re.M)


def _files(root: Path):
    if root.is_symlink() or root.is_file():
        yield root
        return
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            yield Path(folder) / name
        for name in dirs:
            p = Path(folder) / name
            if p.is_symlink():
                yield p


def _link(p: Path, find: re.Pattern, new: bytes) -> bool:
    target = os.readlink(p).encode()
    fixed = find.sub(new, target)
    if fixed == target:
        return False
    st = p.lstat()
    tmp = p.with_name(p.name + ".omabackups-tmp")
    os.symlink(fixed.decode(), tmp)
    os.lchown(tmp, st.st_uid, st.st_gid)
    os.replace(tmp, p)
    return True


def _file(p: Path, find: re.Pattern, new: bytes) -> bool:
    st = p.stat()
    if st.st_size > LIMIT or st.st_size == 0:
        return False
    data = p.read_bytes()
    if b"\0" in data:
        return False
    fixed = find.sub(new, data)
    if fixed == data:
        return False
    tmp = p.with_name(p.name + ".omabackups-tmp")
    tmp.write_bytes(fixed)
    os.chmod(tmp, st.st_mode & 0o7777)
    os.chown(tmp, st.st_uid, st.st_gid)
    os.replace(tmp, p)
    return True


def fix(home: Path, items: list[str], old_home: str, later: list[str] | None = None) -> list[str]:
    """Rewrite the old home folder (/home/OLD) to this one in the items
    (relative to home) that came over. Returns the files changed. Sync apps'
    files are added to `later` instead (when given)."""
    if not old_home or old_home.rstrip("/") == str(home).rstrip("/"):
        return []
    find, repl = pattern(old_home.rstrip("/")), str(home).rstrip("/").encode()
    changed = []
    for item in items:
        for p in _files(home / item):
            rel = str(p.relative_to(home))
            if later is not None and sync_app(rel):
                if p.is_file() and not p.is_symlink() and find.search(p.read_bytes()[:LIMIT]):
                    later.append(rel)
                continue
            try:
                done = _link(p, find, repl) if p.is_symlink() else p.is_file() and _file(p, find, repl)
            except OSError:
                continue
            if done:
                changed.append(str(p.relative_to(home)))
    return changed


def later_file() -> Path:
    from omabackups.core import paths
    return paths.system_state_dir() / "rename-later.json"


def save_later(home: Path, old_home: str, files: list[str]) -> None:
    import json
    from omabackups.core.state import write_atomic
    if files:
        write_atomic(later_file(), json.dumps({"home": str(home), "old_home": old_home,
                                               "files": files}).encode(), 0o600)


def later(user: str) -> list[str]:
    """After Restore my files: stop the sync apps, fix their settings. Returns
    the apps to start again (they were running)."""
    import json
    import subprocess
    import time
    try:
        saved = json.loads(later_file().read_text())
    except (OSError, ValueError):
        return []
    home = Path(saved["home"])
    apps = {sync_app(f) for f in saved["files"]} - {None}
    restart = []
    for name, process in sorted(apps):
        if subprocess.run(["pgrep", "-u", user, "-x", process], capture_output=True).returncode == 0:
            subprocess.run(["pkill", "-u", user, "-x", process], capture_output=True)
            for _ in range(20):
                if subprocess.run(["pgrep", "-u", user, "-x", process], capture_output=True).returncode != 0:
                    break
                time.sleep(0.5)
            restart.append(name)
    fix(home, saved["files"], saved["old_home"])
    later_file().unlink(missing_ok=True)
    return restart
