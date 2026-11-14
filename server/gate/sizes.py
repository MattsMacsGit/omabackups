"""Every folder's size and file count in a restore point (audit 5.4), so
Choose what comes back opens with its sizes at once instead of measuring
over the network.

After each backup the gatekeeper walks the new restore point once, in the
background at idle priority (anything else on the disk goes first, a backup
included). An hourly backup's list only re-measures the folders the backup
changed (and those above them), starting from the line's last list; a full
backup's is walked whole. The list is kept inside the backup (encrypted with
it), beside the restore points: sizes/<point>.json.gz.

  {"version": 1, "parts": {"home": {"": [bytes, files], "u": [...], "u/Documents": [...]},
                           "system": {...}}}
"""

import gzip
import json
import os
import subprocess
import time
from pathlib import Path

import conf
import layout

PARTS = ("home", "system")
VERSION = 1


def folder(inside: Path) -> Path:
    return inside / "sizes"


def list_file(inside: Path, point: str) -> Path:
    return folder(inside) / f"{point}.json.gz"


def dirty_file(inside: Path, point: str) -> Path:
    return folder(inside) / f"{point}.dirty.json"


def running_file(bid: str) -> Path:
    return conf.RUN / "sizes" / bid


def walk(top: Path) -> dict:
    """{folder relative to top: [bytes, files]}, every folder, totals inside it."""
    out = {}

    def visit(path: Path, rel: str) -> list:
        total = [0, 0]
        try:
            entries = list(os.scandir(path))
        except OSError:
            entries = []
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    sub = visit(Path(e.path), f"{rel}/{e.name}".lstrip("/"))
                    total[0] += sub[0]
                    total[1] += sub[1]
                else:
                    total[0] += e.stat(follow_symlinks=False).st_size
                    total[1] += 1
            except OSError:
                continue
        out[rel] = total
        return total

    visit(top, "")
    return out


def update(top: Path, old: dict, dirty: list) -> dict:
    """The last list, with the changed folders (and every folder above them)
    measured again; a folder new since then is walked whole; gone ones go."""
    marked = set()
    for rel in dirty:
        rel = rel.strip("/")
        while True:
            marked.add(rel)
            if not rel:
                break
            rel = rel.rpartition("/")[0]
    new = dict(old)
    for rel in sorted(marked, key=lambda r: r.count("/") + bool(r), reverse=True):
        path = top / rel if rel else top
        gone = not path.is_dir() or path.is_symlink()
        prefix = rel + "/" if rel else ""
        if gone:
            for key in [k for k in new if k == rel or k.startswith(prefix)]:
                del new[key]
            continue
        total, here = [0, 0], set()
        try:
            entries = list(os.scandir(path))
        except OSError:
            entries = []
        for e in entries:
            child = f"{prefix}{e.name}"
            try:
                if e.is_dir(follow_symlinks=False):
                    here.add(child)
                    if child not in marked and child not in new:
                        for key, value in walk(Path(e.path)).items():
                            new[f"{child}/{key}".rstrip("/")] = value
                    sub = new.get(child, [0, 0])
                    total[0] += sub[0]
                    total[1] += sub[1]
                else:
                    total[0] += e.stat(follow_symlinks=False).st_size
                    total[1] += 1
            except OSError:
                continue
        for key in [k for k in new if k.startswith(prefix) and k != rel and "/" not in k[len(prefix):]
                    and k not in here]:
            for sub in [k2 for k2 in new if k2 == key or k2.startswith(key + "/")]:
                del new[sub]                      # a folder that's gone since the last list
        new[rel] = total
    return new


def load(inside: Path, point: str) -> dict | None:
    try:
        with gzip.open(list_file(inside, point), "rt") as f:
            data = json.load(f)
        return data if data.get("version") == VERSION else None
    except (OSError, ValueError):
        return None


def build(inside: Path, point: str) -> dict:
    """The list for one restore point (run in the background, as root)."""
    try:
        dirty = json.loads(dirty_file(inside, point).read_text())
    except (OSError, ValueError):
        dirty = {}
    names = layout.points(inside)
    earlier = [n for n in names if n[:3] == point[:3] and n < point]
    last = load(inside, max(earlier)) if earlier else None
    parts = {}
    for part in PARTS:
        top = inside / "points" / point / part
        changed = dirty.get(part)
        old = (last or {}).get("parts", {}).get(part)
        parts[part] = update(top, old, changed) if changed is not None and old is not None else walk(top)
    data = {"version": VERSION, "parts": parts, "built": int(time.time())}
    folder(inside).mkdir(exist_ok=True)
    tmp = list_file(inside, point).with_suffix(".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, list_file(inside, point))
    dirty_file(inside, point).unlink(missing_ok=True)
    tidy(inside, names)
    return data


def tidy(inside: Path, names: list) -> None:
    """Lists of restore points that are gone go too."""
    try:
        for f in folder(inside).iterdir():
            if f.name.split(".", 1)[0] not in names:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def start(bid: str, inside: Path, point: str, dirty) -> None:
    """After a restore point is made: note what changed, and build its list
    in the background (in tests: straight away)."""
    folder(inside).mkdir(exist_ok=True)
    dirty_file(inside, point).write_text(json.dumps(dirty if isinstance(dirty, dict) else {}))
    if conf.TEST:
        build(inside, point)
        return
    running_file(bid).parent.mkdir(parents=True, exist_ok=True)
    running_file(bid).write_text(point)
    subprocess.run(["systemd-run", f"--unit=omabackups-gate-sizes-{bid[:12]}-{point}", "--collect",
                    "--quiet", "--nice=19", "--property=IOSchedulingClass=idle",
                    "/usr/bin/python3", str(conf.INSTALLED), "sizes", bid, point],
                   capture_output=True, check=False)


def busy(bid: str) -> bool:
    """For the sweep: a list being built keeps the backup open."""
    try:
        point = running_file(bid).read_text().strip()
    except OSError:
        return False
    unit = f"omabackups-gate-sizes-{bid[:12]}-{point}.service"
    done = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, check=False)
    if done.stdout.strip() in ("active", "activating"):
        return True
    running_file(bid).unlink(missing_ok=True)
    return False
