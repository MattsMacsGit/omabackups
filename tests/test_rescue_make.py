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
