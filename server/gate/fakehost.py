"""A pretend box for the automatic tests (test mode only, never as root).

The box is a folder; its "secrets" are kept as hashes; "open" makes the
mount point a link to the folder's insides. Everything above this line
(roles, holds, verbs, the wire) is the real gatekeeper code.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

from host import mountpoint
from registry import Refused


def _h(secret: bytes) -> str:
    return hashlib.sha256(secret).hexdigest()


class FakeHost:
    def create(self, box: Path, size: int, password: bytes, key: bytes, bid: str) -> str:
        if box.exists():
            raise Refused("box exists")
        if size > self.store_free(box.parent):
            raise Refused("not enough space for a box of that size")
        (box / "inside").mkdir(parents=True)
        (box / "secrets.json").write_text(json.dumps([_h(password), _h(key)]))
        self._mount(box, bid)
        return "fake"

    def create_on_device(self, device: Path, password: bytes, key: bytes, bid: str) -> str:
        device.mkdir(parents=True, exist_ok=True)
        (device / "inside").mkdir()
        (device / "secrets.json").write_text(json.dumps([_h(password), _h(key)]))
        self._mount(device, bid)
        return "fake"

    def open(self, box: Path, bid: str, secret: bytes) -> None:
        if _h(secret) not in json.loads((box / "secrets.json").read_text()):   # checked every time
            raise Refused("that password or key doesn't open this backup")
        if not self.is_mounted(bid):
            self._mount(box, bid)

    def _mount(self, box: Path, bid: str) -> None:
        point = mountpoint(bid)
        point.parent.mkdir(parents=True, exist_ok=True)
        point.unlink(missing_ok=True)
        point.symlink_to(box / "inside")

    def close(self, bid: str) -> None:
        mountpoint(bid).unlink(missing_ok=True)

    def change_password(self, box: Path, old: bytes, new: bytes) -> None:
        held = json.loads((box / "secrets.json").read_text())
        if _h(old) != held[0]:
            raise Refused("that isn't your backup's current password")
        held[0] = _h(new)
        (box / "secrets.json").write_text(json.dumps(held))

    def add_computer_key(self, box: Path, password: bytes, key: bytes) -> None:
        held = json.loads((box / "secrets.json").read_text())
        if _h(password) != held[0]:
            raise Refused("that password doesn't open this backup")
        held.append(_h(key))
        (box / "secrets.json").write_text(json.dumps(held))

    def tries_password(self, box: Path, password: bytes) -> bool:
        return _h(password) == json.loads((box / "secrets.json").read_text())[0]

    def writable_copy(self, point: Path, target: Path) -> None:
        shutil.copytree(point, target, symlinks=True)

    def is_open(self, bid: str) -> bool:
        return self.is_mounted(bid)

    def is_mounted(self, bid: str) -> bool:
        return mountpoint(bid).is_symlink()

    def activity(self, bid: str) -> str | None:
        if not self.is_mounted(bid):
            return None
        # Tests write this file to pretend the disk is busy.
        try:
            return (mountpoint(bid) / ".activity").read_text()
        except OSError:
            return "quiet"

    def make_subvolume(self, path: Path) -> None:
        path.mkdir()

    def clone(self, source: Path, target: Path) -> None:
        if source.is_dir():
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target)

    def snapshot(self, source: Path, target: Path) -> None:
        shutil.copytree(source, target, symlinks=True)

    def delete_subvolume(self, path: Path) -> None:
        shutil.rmtree(path)

    def used_inside(self, bid: str) -> tuple[int, int]:
        used = sum(f.stat().st_size for f in mountpoint(bid).resolve().rglob("*") if f.is_file())
        return used, int(os.environ.get("OMABACKUPS_GATE_FAKE_INSIDE_FREE", str(50 << 30)))

    def store_free(self, store: Path) -> int:
        return int(os.environ.get("OMABACKUPS_GATE_FAKE_FREE", str(100 << 30)))

    def remove_box(self, box: Path, bid: str) -> None:
        self.close(bid)
        shutil.rmtree(box, ignore_errors=True)
