"""Sizes from the Pi's list of every folder in a restore point (audit 5.4;
server/gate/sizes.py), so Choose what comes back opens with its numbers at
once instead of measuring over the network."""

import bisect
import fnmatch


def under(folders: dict, rel: str) -> list[str]:
    """The folders inside rel (its whole tree), in order."""
    keys = sorted(folders)
    prefix = rel + "/" if rel else ""
    start = bisect.bisect_left(keys, prefix)
    out = []
    for key in keys[start:]:
        if not key.startswith(prefix):
            break
        out.append(key)
    return out


def from_list(folders: dict, rel: str, skips, quiet) -> tuple[int, int, int]:
    """(what comes back, the whole folder, how many things inside are left
    out). Folders left out are taken off; files left out on their own aren't
    in the list (they're small next to folders)."""
    whole = folders[rel][0]
    left, inside, tops = 0, 0, set()
    for key in under(folders, rel):
        parts = key.split("/")
        if key == rel or any("/".join(parts[:i]) in tops for i in range(1, len(parts))):
            continue                       # inside something already left out
        if skips.skipped(key):
            tops.add(key)
            left += folders[key][0]
            inside += 0 if quiet(key) else 1
    return whole - left, whole, inside


def quick_size(known: dict, rules: dict, user: str) -> int:
    """What a Quick skips switch covers, from the lists."""
    total = 0
    for part, items in rules.items():
        folders = known.get(part) or {}
        found = []
        for rule in items:
            if rule.startswith("/"):
                pattern = rule.lstrip("/")
                found += [k for k in folders if fnmatch.fnmatchcase(k, pattern)]
            else:
                body = rule.removeprefix("**/")
                found += [k for k in folders if k == f"{user}/{body}" or fnmatch.fnmatchcase(k, f"{user}/*/{body}")]
        tops = []
        for key in sorted(set(found)):
            if not any(key.startswith(t + "/") for t in tops):
                tops.append(key)
                total += folders[key][0]
    return total
