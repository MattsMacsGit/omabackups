"""The disk list: every disk, warned, only the running system's own left out."""

from omabackups.setup import disks

SERVER = {"blockdevices": [
    {"name": "sda", "path": "/dev/sda", "size": 4000787030016, "model": "BIG USB DISK", "tran": "usb",
     "type": "disk", "rm": False, "children": [
         {"name": "sda1", "path": "/dev/sda1", "size": 4000785960960, "type": "part",
          "fstype": "ext4", "label": "data", "mountpoints": ["/mnt/data"]}]},
    {"name": "sdb", "path": "/dev/sdb", "size": 2000398934016, "model": "OLD BACKUP", "tran": "usb",
     "type": "disk", "rm": False, "children": [
         {"name": "sdb1", "path": "/dev/sdb1", "size": 1073741824, "type": "part", "fstype": "vfat",
          "label": "OMABOOT", "mountpoints": [None]},
         {"name": "sdb3", "path": "/dev/sdb3", "size": 1980000000000, "type": "part",
          "fstype": "crypto_LUKS", "mountpoints": [None]}]},
    {"name": "sdc", "path": "/dev/sdc", "size": 64000000000, "model": "STICK", "tran": "usb",
     "type": "disk", "rm": True, "children": []},
    {"name": "mmcblk0", "path": "/dev/mmcblk0", "size": 31900000000, "model": None, "tran": None,
     "type": "disk", "rm": False, "children": [
         {"name": "mmcblk0p2", "path": "/dev/mmcblk0p2", "size": 31000000000, "type": "part",
          "fstype": "ext4", "label": "rootfs", "mountpoints": ["/"]}]},
    {"name": "zram0", "path": "/dev/zram0", "size": 2000000000, "type": "disk", "children": []},
]}
SYSTEM = {"blockdevices": [{"name": "mmcblk0p2", "path": "/dev/mmcblk0p2", "type": "part",
                            "children": [{"name": "mmcblk0", "path": "/dev/mmcblk0", "type": "disk"}]}]}


def test_a_server_like_layout():
    found = {d.path: d for d in disks.listing(SERVER, disks.disks_in(SYSTEM))}
    assert set(found) == {"/dev/sda", "/dev/sdb", "/dev/sdc"}      # not the system's, not memory
    assert any("in use: mounted at /mnt/data" in w for w in found["/dev/sda"].warnings)
    assert any("OmaBackups backup disk" in w for w in found["/dev/sdb"].warnings)
    assert any("can't see inside" in w for w in found["/dev/sdb"].warnings)
    assert any("No partitions" in w for w in found["/dev/sdc"].warnings)
    for d in found.values():
        assert d.warnings[-1] == "Everything on it will be erased."
