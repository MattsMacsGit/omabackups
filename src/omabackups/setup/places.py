"""Where on a backup server a backup can go (D30): every disk, with its size,
its free space and what's on it. You pick a disk, then the whole disk
(erased) or its free space (nothing erased: OmaBackups makes its own folder
at the top of that disk). Nobody types a path.

The server's own system disk is listed for its free space only: it can't be
erased while the server runs from it.
"""

from dataclasses import dataclass, field

from omabackups.backup.check import human
from omabackups.setup import disks

COLUMNS = disks.COLUMNS + ",FSAVAIL"
FOLDER = "omabackups-store"
# Mounts that are never a home for a backup (they're small and the system's own).
NOT_HERE = ("/boot", "/efi", "[SWAP]")


@dataclass
class Place:
    path: str
    size: int
    model: str
    transport: str
    removable: bool
    system: bool = False
    free: int = 0               # free space where the folder would go
    mount: str = ""             # the mount it would go in ("" = nothing mounted)
    store: str = ""             # this server's backup store, if it's on this disk
    contents: list = field(default_factory=list)

    @property
    def name(self) -> str:
        what = self.model or "Disk"
        if self.system:
            return f"{what} (the server's system disk)"
        return f"{what} ({'USB' if self.transport == 'usb' else self.transport or 'internal'})"

    def line(self) -> str:
        free = f"{human(self.free)} free" if self.mount else "nothing mounted"
        return f"{self.name}  ·  {human(self.size)}  ·  {free}  ·  {self.path}"

    @property
    def folder(self) -> str:
        """The folder its free space would use: the store already here, else a new one."""
        if self.store:
            return self.store
        if self.mount == "/":
            return f"/srv/{FOLDER}"
        return f"{self.mount.rstrip('/')}/{FOLDER}"


def _mounts(node: dict) -> list[tuple[str, int]]:
    """Every (mount point, free bytes) at or under this node."""
    found = []
    for mount in node.get("mountpoints") or []:
        if mount and not mount.startswith(NOT_HERE):
            found.append((mount, int(node.get("fsavail") or 0)))
    for child in node.get("children") or []:
        found.extend(_mounts(child))
    return found


def _store_mount(mounts: list[tuple[str, int]], store: str) -> tuple[str, int] | None:
    """The mount that holds the store folder (the longest one it sits under)."""
    under = [m for m in mounts if store == m[0] or store.startswith(m[0].rstrip("/") + "/")]
    return max(under, key=lambda m: len(m[0]), default=None)


def places(tree: dict, system: set[str], store: str = "") -> list[Place]:
    """Every disk in the server's lsblk tree, as a Place."""
    out = []
    for node in tree.get("blockdevices", []):
        if node.get("type") != "disk" or int(node.get("size") or 0) == 0:
            continue
        if node["name"].startswith(("zram", "ram")):
            continue
        place = Place(node["path"], int(node["size"]), (node.get("model") or "").strip(),
                      node.get("tran") or "", bool(node.get("rm")), system=node["path"] in system)
        mounts = _mounts(node)
        held = _store_mount(mounts, store) if store else None
        if held:
            place.mount, place.free, place.store = held[0], held[1], store
        elif mounts:
            place.mount, place.free = max(mounts, key=lambda m: m[1])
        listed = disks.listing({"blockdevices": [node]}, set())
        place.contents = [w for w in (listed[0].warnings if listed else [])
                          if w != "Everything on it will be erased."]
        if place.store:
            place.contents.insert(0, "This server's backup store is on it: other "
                                     "computers' backups may be there too.")
        out.append(place)
    # The disks with the most room first; the system disk last.
    return sorted(out, key=lambda p: (p.system, -p.free))


def sizes(free: int) -> list[int]:
    """Sizes to offer for a backup in free space, in GB: a quarter, half and
    three quarters of what's free (never under 1 GB, never the same twice)."""
    gb = free >> 30
    offered = []
    for share in (4, 2, 4 / 3):
        n = int(gb / share)
        n = n - n % 10 if n >= 50 else n     # round numbers once they're big
        if n >= 1 and n not in offered:
            offered.append(n)
    return offered or ([gb] if gb >= 1 else [])
