"""Letting go of someone else's mount from a root job: root jobs have their
own view of the mounts (PrivateTmp), so an unmount there left the desktop's
mount of a stick in place and Make Rescue USB failed with "Device or resource
busy" every time it was tried on a stick the desktop had opened."""

from omabackups.core import mounts


def _views(monkeypatch, mine, computers):
    def readlink(path):
        if path == "/proc/1/ns/mnt" and computers is None:
            raise PermissionError(path)
        return mine if path == "/proc/self/ns/mnt" else computers
    monkeypatch.setattr(mounts.os, "readlink", readlink)


def test_a_root_job_unmounts_in_the_computers_own_view(monkeypatch):
    _views(monkeypatch, "mnt:[1]", "mnt:[2]")
    assert mounts.umount_command("/dev/sdz3") == ["nsenter", "--mount=/proc/1/ns/mnt", "--", "umount", "/dev/sdz3"]


def test_with_one_view_it_is_a_plain_unmount(monkeypatch):
    _views(monkeypatch, "mnt:[1]", "mnt:[1]")          # the Rescue USB, or no private view
    assert mounts.umount_command("-R", "/mnt/x") == ["umount", "-R", "/mnt/x"]


def test_when_the_views_cant_be_read_it_is_a_plain_unmount(monkeypatch):
    _views(monkeypatch, "mnt:[1]", None)               # not root
    assert mounts.umount_command("/dev/sdz3") == ["umount", "/dev/sdz3"]


def test_the_root_jobs_free_disks_through_it():
    from pathlib import Path
    src = Path(mounts.__file__).resolve().parent.parent
    for rel in ("restore/newdisk.py", "root/job_rescue.py", "root/job_disk.py"):
        assert "mounts." in (src / rel).read_text(), rel
