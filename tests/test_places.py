"""D30: where on a backup server a backup can go: pick a disk, then the whole
disk or its free space. Nobody types a path."""

from omabackups.setup import places

GB = 1 << 30


def tree():
    """A server like a small home server: a system card, a data disk with
    something on it, and an empty USB stick."""
    return {"blockdevices": [
        {"name": "mmcblk0", "path": "/dev/mmcblk0", "size": 32 * GB, "type": "disk", "model": None,
         "tran": None, "rm": False, "mountpoints": [None], "children": [
             {"name": "mmcblk0p1", "path": "/dev/mmcblk0p1", "size": GB // 2, "type": "part",
              "fstype": "vfat", "mountpoints": ["/boot/firmware"], "fsavail": GB // 4},
             {"name": "mmcblk0p2", "path": "/dev/mmcblk0p2", "size": 31 * GB, "type": "part",
              "fstype": "ext4", "mountpoints": ["/"], "fsavail": 20 * GB}]},
        {"name": "sda", "path": "/dev/sda", "size": 2000 * GB, "type": "disk", "model": "Data Disk",
         "tran": "usb", "rm": False, "mountpoints": [None], "children": [
             {"name": "sda1", "path": "/dev/sda1", "size": 2000 * GB, "type": "part",
              "fstype": "ext4", "label": "media", "mountpoints": ["/mnt/media"],
              "fsavail": 1200 * GB}]},
        {"name": "sdb", "path": "/dev/sdb", "size": 64 * GB, "type": "disk", "model": "Stick",
         "tran": "usb", "rm": True, "mountpoints": [None]},
        {"name": "zram0", "path": "/dev/zram0", "size": 2 * GB, "type": "disk", "mountpoints": ["[SWAP]"]},
    ]}


def test_every_disk_is_listed_most_room_first_and_the_system_disk_last():
    found = places.places(tree(), {"/dev/mmcblk0"})
    assert [p.path for p in found] == ["/dev/sda", "/dev/sdb", "/dev/mmcblk0"]
    assert found[-1].system and "system disk" in found[-1].name


def test_free_space_gets_a_folder_of_its_own_at_the_top_of_the_disk():
    data = places.places(tree(), {"/dev/mmcblk0"})[0]
    assert data.free == 1200 * GB and data.mount == "/mnt/media"
    assert data.folder == "/mnt/media/omabackups-store"
    assert "1.3 TB free" in data.line() or "1.2 TB free" in data.line()
    assert any('named "media"' in w for w in data.contents)
    assert not any("erased" in w for w in data.contents)


def test_the_system_disk_offers_its_free_space_but_not_its_boot_partition():
    card = places.places(tree(), {"/dev/mmcblk0"})[-1]
    assert card.mount == "/" and card.free == 20 * GB
    assert card.folder == "/srv/omabackups-store"


def test_a_disk_with_nothing_mounted_has_no_free_space_to_offer():
    stick = places.places(tree(), {"/dev/mmcblk0"})[1]
    assert stick.mount == "" and "nothing mounted" in stick.line()


def test_the_store_already_on_a_disk_is_used_again():
    data = places.places(tree(), {"/dev/mmcblk0"}, store="/mnt/media/backups/omabackups")[0]
    assert data.folder == "/mnt/media/backups/omabackups"
    assert "backup store is on it" in data.contents[0]


def test_sizes_offered_are_shares_of_the_free_space():
    assert places.sizes(1200 * GB) == [600, 1160]     # D50: half (suggested), all of it
    assert places.sizes(20 * GB) == [10, 19]
    assert places.sizes(GB) == [1]
    assert places.sizes(GB // 2) == []
