"""Make Rescue USB (9c): the image is kept and recognised by its checksum; a
download that doesn't match is never used; the root job writes only the
image in the user's own download folder."""

import hashlib

import pytest

from omabackups.core.errors import OmaError
from omabackups.setup import rescue_image as image


def test_a_kept_image_is_recognised_by_its_checksum(sandbox):
    image.folder().mkdir(parents=True)
    image.path().write_bytes(b"rescue system")
    sha = hashlib.sha256(b"rescue system").hexdigest()
    assert image.checksum(image.path()) == sha
    assert not image.have({"sha256": sha})                      # no record of it yet
    (image.folder() / (image.NAME + ".sha256")).write_text(sha + "\n")
    assert image.have({"sha256": sha})
    assert not image.have({"sha256": "0" * 64})                 # a newer one is published


def test_a_download_that_doesnt_match_is_never_used(sandbox, monkeypatch):
    image.folder().mkdir(parents=True)

    def fake_curl(*args, capture=True):
        image.path().with_suffix(".part").write_bytes(b"not it")
        return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(image, "_curl", fake_curl)
    with pytest.raises(OmaError) as caught:
        image.download({"sha256": "0" * 64, "version": "x"})
    assert caught.value.code == "rescue-checksum"
    assert not image.path().exists() and image.path().with_suffix(".bad").exists()


def test_the_root_job_writes_only_the_users_own_image(sandbox, monkeypatch, tmp_path):
    from omabackups.backup import run
    from omabackups.root import job_rescue
    import getpass
    monkeypatch.setattr(run, "linked_user", lambda: getpass.getuser())
    with pytest.raises(OmaError):
        job_rescue._image({"image": "/etc/passwd"})
    stray = tmp_path / image.NAME
    stray.write_bytes(b"x")
    with pytest.raises(OmaError):
        job_rescue._image({"image": str(stray)})                # not under the user's home


def test_an_old_settings_part_past_the_image_is_blanked(sandbox, monkeypatch, tmp_path):
    """A stick made before keeps its settings part past the image; the desktop
    opened it again as soon as it reappeared and it couldn't be formatted."""
    from omabackups.root import job_rescue
    monkeypatch.setattr(job_rescue, "CLEAR", 3 << 20)
    img, disk = tmp_path / "rescue.iso", tmp_path / "stick"
    img.write_bytes(b"R" * (5 << 20))
    job_rescue._copy(img, str(disk))
    written = disk.read_bytes()
    assert written[:5 << 20] == img.read_bytes()
    assert written[5 << 20:] == bytes(3 << 20)


def test_a_settings_part_the_desktop_opened_is_let_go_and_formatted(monkeypatch):
    import subprocess
    from omabackups.root import job_rescue
    calls, state = [], {"mounted": True, "busy": 2}

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        code = 0
        if cmd[0] == "findmnt":
            code = 0 if state["mounted"] else 1
        elif cmd[0] == "umount":
            state["mounted"] = False
        elif cmd[0] == "mkfs.fat":
            if state["busy"]:
                state["busy"] -= 1
                state["mounted"] = True             # opened again behind our back
                code = 1
        return subprocess.CompletedProcess(cmd, code, b"", b"Device or resource busy" if code else b"")
    monkeypatch.setattr(job_rescue.subprocess, "run", fake_run)
    monkeypatch.setattr(job_rescue.time, "sleep", lambda s: None)
    job_rescue._format("/dev/sdz3")
    assert calls.count("mkfs.fat") == 3 and calls.count("umount") == 3


def test_a_part_that_stays_busy_says_so_with_the_details(monkeypatch):
    import subprocess
    from omabackups.root import job_rescue
    monkeypatch.setattr(job_rescue.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0 if cmd[0] == "findmnt" else 1, b"", b"mkfs.fat: unable to open /dev/sdz3: Device or resource busy"))
    monkeypatch.setattr(job_rescue.time, "sleep", lambda s: None)
    with pytest.raises(OmaError) as caught:
        job_rescue._format("/dev/sdz3")
    assert caught.value.code == "rescue-usb" and "busy" in caught.value.details
