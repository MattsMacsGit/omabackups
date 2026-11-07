"""Stands in for this computer's btrfs snapshots in tests.

Each part is a plain folder; a "snapshot" is a copy; the change list is
written in btrfs's dump format by comparing two copies (new files arrive
through temporary names, as btrfs does). Renames show up as delete + new
(btrfs's own renames are covered by test_changes.py and the live check).
"""

import os
import shutil
from pathlib import Path

from omabackups.backup.source import Part


class FakeSnapshots:
    def __init__(self, store: Path, part: Part):
        self.store, self.part = store, part
        store.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def path(self, name: str) -> Path:
        return self.store / name

    def take(self, part: Part, run: str) -> Path:
        target = self.path(f"{part.name}-{run}")
        n = 1
        while target.exists():
            n += 1
            target = self.path(f"{part.name}-{run}-{n}")
        shutil.copytree(part.mount, target, symlinks=True, copy_function=shutil.copy2)
        return target

    def exists(self, name: str) -> bool:
        return bool(name) and self.path(name).is_dir()

    def dump(self, since: str, new: Path) -> str:
        old, lines, n = self.path(since), [], 300
        esc = lambda p: p.replace(" ", "\\ ")   # noqa: E731
        before = {str(p.relative_to(old)) for p in old.rglob("*")}
        after = {str(p.relative_to(new)) for p in new.rglob("*")}
        for rel in sorted(before - after, reverse=True):
            lines.append(f"{'rmdir' if (old / rel).is_dir() else 'unlink'} ./{new.name}/{esc(rel)}")
        for rel in sorted(after - before):
            n += 1
            kind = "mkdir" if (new / rel).is_dir() else "mkfile"
            lines.append(f"{kind} ./{new.name}/o{n}-1-0")
            lines.append(f"rename ./{new.name}/o{n}-1-0 dest=./{new.name}/{esc(rel)}")
        for rel in sorted(after & before):
            a, b = old / rel, new / rel
            if a.is_file() and b.is_file() and a.read_bytes() != b.read_bytes():
                lines.append(f"update_extent ./{new.name}/{esc(rel)} offset=0 len={b.stat().st_size}")
        return "\n".join([f"snapshot ./{new.name} uuid=x transid=1", *lines]) + "\n"

    def drop(self, name: str) -> None:
        if name and self.path(name).exists():
            shutil.rmtree(self.path(name))

    def names(self) -> list[str]:
        return sorted(os.listdir(self.store))


class FakeSource:
    def __init__(self, root: Path):
        self.root = root
        self.list = [Part("system", str(root / "system"), True, "fake", "@"),
                     Part("home", str(root / "home"), True, "fake", "@home"),
                     Part("boot", str(root / "boot"), False)]
        for part in self.list:
            Path(part.mount).mkdir(parents=True, exist_ok=True)

    def parts(self):
        return self.list

    def snapshots(self, part):
        return FakeSnapshots(self.root / "snaps", part)
