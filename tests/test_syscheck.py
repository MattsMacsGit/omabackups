"""The system check at setup (audit 7.5; 1.x lib/detect.py): warn, never block."""

from omabackups.setup import syscheck

OMARCHY = """\
22 1 0:30 /@ / rw,relatime shared:1 - btrfs /dev/mapper/root rw,subvol=/@
23 22 0:30 /@home /home rw,relatime shared:2 - btrfs /dev/mapper/root rw,subvol=/@home
24 22 259:1 / /boot rw,relatime shared:3 - vfat /dev/nvme0n1p1 rw
"""
PLAIN = """\
22 1 259:2 / / rw,relatime shared:1 - ext4 /dev/sda2 rw
"""


def crypt(tmp_path, dm="dm-0"):
    (tmp_path / "sys/block" / dm / "dm").mkdir(parents=True)
    (tmp_path / "sys/block" / dm / "dm/uuid").write_text("CRYPT-LUKS2-0123-root\n")


def test_an_omarchy_install_is_fine(tmp_path):
    crypt(tmp_path)
    info = OMARCHY.replace("/dev/mapper/root", "/dev/dm-0")
    assert syscheck.problems(info, tmp_path) == []


def test_each_thing_that_doesnt_fit_is_named(tmp_path):
    assert syscheck.problems(PLAIN, tmp_path) == [syscheck.NOT_BTRFS, syscheck.HOME_ELSEWHERE,
                                                  syscheck.NO_BOOT, syscheck.NOT_ENCRYPTED]
    unencrypted = OMARCHY.replace("/dev/mapper/root", "/dev/nvme0n1p2")
    assert syscheck.problems(unencrypted, tmp_path) == [syscheck.NOT_ENCRYPTED]
