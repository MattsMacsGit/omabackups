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


def test_an_old_rescue_usb_says_what_its_locked_part_is():
    """Its settings part showed as "can't see inside: it may hold a system or
    files" (demo film, 14 Nov): it's the Rescue USB's own settings."""
    stick = {"blockdevices": [
        {"name": "sdb", "path": "/dev/sdb", "size": 8589934592, "model": "STICK", "tran": "usb",
         "type": "disk", "rm": True, "children": [
             {"name": "sdb1", "path": "/dev/sdb1", "size": 964689920, "type": "part", "fstype": "iso9660",
              "label": "OMABACKUPS_RESCUE", "mountpoints": [None]},
             {"name": "sdb3", "path": "/dev/sdb3", "size": 67108864, "type": "part",
              "fstype": "crypto_LUKS", "label": "OMABACKUPS", "mountpoints": [None]}]}]}
    found = disks.listing(stick, set())[0]
    assert any("a Rescue USB's own settings, locked" in w for w in found.warnings)
    assert not any("can't see inside" in w for w in found.warnings)


def test_a_new_server_is_trusted_the_first_time_without_a_raw_question(sandbox, tmp_path):
    """Setup showed ssh's own "yes/no/[fingerprint]" question (demo film):
    accept-new as 1.x did, and a changed key is still refused."""
    from omabackups.where import ssh
    cmd = ssh.as_user("192.0.2.10", "pi", tmp_path / "known_hosts")
    assert "StrictHostKeyChecking=accept-new" in cmd and "LogLevel=ERROR" in cmd
    assert "StrictHostKeyChecking=yes" in ssh.gatekeeper_ssh()
