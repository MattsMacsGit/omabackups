"""The old user name in the settings that came over (D41).

Only when the user name changed: in the settings Migrate just brought back,
`/home/<old>` becomes `/home/<new>`, so a setting that names a folder (git's
GitHub login helper, a download folder, a link into ~/.local) points at this
computer's home. The person had the backup's password: it's their setup,
only the name changed.

Small text files only (no NUL byte, 1 MB at most), and links. Owner and
permissions are kept. Caches are skipped.
"""

import os
import re
from pathlib import Path

LIMIT = 1_000_000
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


def fix(home: Path, items: list[str], old_home: str) -> list[str]:
    """Rewrite the old home folder (/home/OLD) to this one in the items
    (relative to home) that came over. Returns the files changed."""
    if not old_home or old_home.rstrip("/") == str(home).rstrip("/"):
        return []
    find, repl = pattern(old_home.rstrip("/")), str(home).rstrip("/").encode()
    changed = []
    for item in items:
        for p in _files(home / item):
            try:
                done = _link(p, find, repl) if p.is_symlink() else p.is_file() and _file(p, find, repl)
            except OSError:
                continue
            if done:
                changed.append(str(p.relative_to(home)))
    return changed
