"""The skip list: what isn't backed up (any file or folder, as 1.x).

Each entry is an rsync-style pattern, relative to the part (system or home):
  /tmp            anchored: only that path at the top of the part
  .cache          a name: matches at any depth
  **/Trash        the same, written the long way
  .var/app/*/cache   * matches inside one name
The same list goes to rsync (full backups) and filters the change list
(everyday backups), so both skip exactly the same things.
"""

import fnmatch
import hashlib
import json

from omabackups.core import paths

# 1.x's proven defaults. The picker (stage 5) lets the user change the list.
DEFAULTS = {
    "system": ["/tmp", "/var/tmp", "/swap", "/swapfile", "/lost+found",
               "/var/lib/systemd/coredump", "/var/cache/pacman/pkg",
               "/.snapshots", "/var/lib/docker"],
    "home": ["**/.local/share/Trash", ".Trash", ".cache", ".thumbnails", "lost+found",
             ".var/app/*/cache"],
    "boot": [],
}


class Skips:
    def __init__(self, patterns: list[str]):
        self.patterns = [p.strip().rstrip("/") for p in patterns if p.strip() and not p.startswith("#")]
        self._anchored = [p.lstrip("/").split("/") for p in self.patterns if p.startswith("/")]
        self._floating = [p.removeprefix("**/").split("/") for p in self.patterns
                          if not p.startswith("/")]

    def skipped(self, rel: str) -> bool:
        """Is this path (relative to the part), or a folder it's in, skipped?"""
        parts = [p for p in rel.split("/") if p]
        for pattern in self._anchored:
            if len(parts) >= len(pattern) and all(
                    fnmatch.fnmatchcase(a, b) for a, b in zip(parts, pattern)):
                return True
        for pattern in self._floating:
            n = len(pattern)
            for start in range(0, len(parts) - n + 1):
                if all(fnmatch.fnmatchcase(a, b) for a, b in zip(parts[start:start + n], pattern)):
                    return True
        return False

    def rsync_rules(self) -> list[str]:
        """--exclude rules meaning exactly the same as skipped(): rsync reads
        the patterns the same way (a leading / anchors; otherwise a pattern
        matches the end of a path at any depth; * stays inside one name)."""
        return [f"--exclude={p}" for p in self.patterns]

    def fingerprint(self) -> str:
        """Changes when the list changes (then the next backup is a full check)."""
        return hashlib.sha256(json.dumps(sorted(self.patterns)).encode()).hexdigest()[:16]


def for_part(part: str) -> Skips:
    """The defaults plus the user's own list for this part (if any)."""
    extra = []
    try:
        saved = json.loads((paths.system_config_dir() / "skips.json").read_text())
        extra = [p for p in saved.get(part, []) if isinstance(p, str)]
    except (OSError, ValueError, AttributeError):
        pass
    return Skips(DEFAULTS.get(part, []) + extra)
