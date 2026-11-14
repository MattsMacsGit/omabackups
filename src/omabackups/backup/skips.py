"""The skip list: what isn't backed up (any file or folder, as 1.x).

Each entry is an rsync-style pattern, relative to the part (system or home):
  /tmp            anchored: only that path at the top of the part
  .cache          a name: matches at any depth
  **/Trash        the same, written the long way
  .var/app/*/cache   * matches inside one name
  !/u/.cache      an exception: back this one up although a rule skips it
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
    """Rules are checked like rsync does: in order, first match wins, and a
    skipped folder's contents are never looked at. The order: exact paths
    (deepest first; "!" exceptions before skips at the same depth), then the
    any-depth names. "!/u/.cache" backs up that one .cache although ".cache"
    is skipped everywhere else."""

    def __init__(self, patterns: list[str]):
        self.patterns = [p.strip().rstrip("/") for p in patterns if p.strip() and not p.startswith("#")]
        anchored, floating = [], []
        for p in self.patterns:
            keep = p.startswith("!")
            body = p[1:] if keep else p
            if body.startswith("/"):
                anchored.append((body.lstrip("/").split("/"), keep, p))
            elif not keep:
                floating.append((body.removeprefix("**/").split("/"), False, p))
        anchored.sort(key=lambda r: (-len(r[0]), not r[1]))
        self._rules = anchored + floating

    def _first(self, parts: list[str]):
        """The first rule matching this exact path (not its folders), or None."""
        n = len(parts)
        for pattern, keep, raw in self._rules:
            if raw.lstrip("!").startswith("/"):
                if len(pattern) == n and all(fnmatch.fnmatchcase(a, b) for a, b in zip(parts, pattern)):
                    return keep, raw
            elif n >= len(pattern) and all(
                    fnmatch.fnmatchcase(a, b) for a, b in zip(parts[n - len(pattern):], pattern)):
                return keep, raw
        return None

    def why(self, rel: str) -> tuple[str, str] | None:
        """(the rule, the folder it skipped) when rel is skipped, else None."""
        parts = [p for p in rel.split("/") if p]
        for depth in range(1, len(parts) + 1):
            hit = self._first(parts[:depth])
            if hit and not hit[0]:
                return hit[1], "/".join(parts[:depth])
        return None

    def skipped(self, rel: str) -> bool:
        """Is this path (relative to the part), or a folder it's in, skipped?"""
        return self.why(rel) is not None

    def rsync_rules(self) -> list[str]:
        """The same rules for rsync, in the same order (rsync: first match wins)."""
        return [f"--include={raw[1:]}" if keep else f"--exclude={raw}" for _, keep, raw in self._rules]

    def fingerprint(self) -> str:
        """Changes when the list changes (then the next backup is a full check)."""
        return hashlib.sha256(json.dumps(sorted(self.patterns)).encode()).hexdigest()[:16]


def saved() -> dict:
    try:
        data = json.loads((paths.system_config_dir() / "skips.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def patterns_for(part: str) -> list[str]:
    """The whole list for a part. Once the picker has saved (format 2) it holds
    the complete list, defaults included, so a default can be ticked back on;
    before that, the defaults (plus any extras of the older format)."""
    from omabackups.tui.quick import upgrade
    data = saved()
    mine = upgrade([p for p in data.get(part, []) if isinstance(p, str)])
    if data.get("format") == 2 and part in data:
        return mine
    return DEFAULTS.get(part, []) + mine


def for_part(part: str) -> Skips:
    return Skips(patterns_for(part))
