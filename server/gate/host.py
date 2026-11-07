"""The root jobs on the server: the encrypted box (a LUKS2 container file)
and the btrfs filesystem inside it (BUILD 5.4, D6, D25).

Secrets reach cryptsetup through files in a root-only folder on /run (a
memory filesystem), deleted straight after: never on a command line, where
any user could read them.
"""

import os
import secrets
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import conf
from registry import Refused

ADIANTUM = "xchacha12,aes-adiantum-plain64"
AES_XTS = "aes-xts-plain64"


def run(*cmd: str, quiet: bool = False) -> str:
    done = subprocess.run(list(cmd), capture_output=True, text=True)
    if done.returncode != 0:
        why = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no message"]
        raise Refused(f"{cmd[0]} failed: {why[0]}")
    return done.stdout


def has_aes() -> bool:
    """D25: aes-xts where the CPU has AES instructions, adiantum where not."""
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="ascii", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        if line.lower().startswith(("flags", "features")) and "aes" in line.split(":", 1)[1].split():
            return True
    return False


def cipher() -> tuple[str, str]:
    return (AES_XTS, "512") if has_aes() else (ADIANTUM, "256")


@contextmanager
def secret_files(*values: bytes):
    folder = conf.RUN / "secrets"
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    made = []
    try:
        for value in values:
            fd, path = tempfile.mkstemp(dir=folder)
            with os.fdopen(fd, "wb") as f:
                f.write(value)
            made.append(path)
        yield made
    finally:
        for path in made:
            Path(path).unlink(missing_ok=True)


def mapper(bid: str) -> str:
    return f"omabackups-gate-{bid[:12]}"


def mountpoint(bid: str) -> Path:
    return conf.RUN / "boxes" / bid


class RealHost:
    def create(self, box: Path, size: int, password: bytes, key: bytes, bid: str) -> str:
        box.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(box.parent, 0o700)
        with open(box, "xb") as f:
            os.chmod(box, 0o600)
            try:
                os.posix_fallocate(f.fileno(), 0, size)  # the space is really there
            except OSError as exc:
                box.unlink(missing_ok=True)
                raise Refused(f"not enough space for a box of that size ({exc.strerror})")
        try:
            return self._format(box, password, key, bid)
        except BaseException:
            box.unlink(missing_ok=True)
            raise

    def create_on_device(self, device: Path, password: bytes, key: bytes, bid: str) -> str:
        """A backup disk plugged into the computer: the box is its partition."""
        return self._format(device, password, key, bid)

    def _format(self, box: Path, password: bytes, key: bytes, bid: str) -> str:
        name, bits = cipher()
        try:
            with secret_files(password, key) as (pw, kf):
                run("cryptsetup", "luksFormat", "--batch-mode", "--type", "luks2",
                    "--cipher", name, "--key-size", bits, "--pbkdf", "argon2id",
                    "--label", f"omabackups-{bid[:12]}", "--key-file", pw, str(box))
                run("cryptsetup", "luksAddKey", "--batch-mode", "--pbkdf", "argon2id",
                    "--key-file", pw, str(box), kf)
                run("cryptsetup", "open", "--type", "luks2", "--key-file", kf, str(box), mapper(bid))
            run("mkfs.btrfs", "-q", "-L", "omabackups", f"/dev/mapper/{mapper(bid)}")
            self._mount(bid)
        except BaseException:
            self.close(bid)
            raise
        return name

    def open(self, box: Path, bid: str, secret: bytes) -> None:
        """Unlock. The secret is checked EVERY time, also when the backup is open
        already (for another job): an open backup is no way in without it."""
        with secret_files(secret) as (kf,):
            try:
                if self.is_open(bid):
                    run("cryptsetup", "open", "--test-passphrase", "--type", "luks2",
                        "--key-file", kf, str(box))
                else:
                    run("cryptsetup", "open", "--type", "luks2", "--key-file", kf, str(box), mapper(bid))
            except Refused as exc:
                raise Refused("that password or key doesn't open this backup") from exc
        if not self.is_mounted(bid):
            self._mount(bid)

    def _mount(self, bid: str) -> None:
        point = mountpoint(bid)
        point.mkdir(parents=True, exist_ok=True)
        run("mount", "-o", "noatime", f"/dev/mapper/{mapper(bid)}", str(point))
        os.chmod(point, 0o700)

    def close(self, bid: str) -> None:
        if self.is_mounted(bid):
            run("sync")
            run("umount", str(mountpoint(bid)))
        if self.is_open(bid):
            run("cryptsetup", "close", mapper(bid))

    def change_password(self, box: Path, old: bytes, new: bytes) -> None:
        """Replace the password slot (the one `old` opens) with `new`."""
        with secret_files(old, new) as (oldf, newf):
            try:
                run("cryptsetup", "luksChangeKey", "--batch-mode", "--pbkdf", "argon2id",
                    "--key-file", oldf, str(box), newf)
            except Refused as exc:
                raise Refused("that isn't your backup's current password") from exc

    def is_open(self, bid: str) -> bool:
        return Path("/dev/mapper", mapper(bid)).exists()

    def is_mounted(self, bid: str) -> bool:
        return os.path.ismount(mountpoint(bid))

    def activity(self, bid: str) -> str | None:
        """The box's read/write counters, or None if it isn't open."""
        try:
            dm = os.path.basename(os.path.realpath(f"/dev/mapper/{mapper(bid)}"))
            return Path("/sys/block", dm, "stat").read_text(encoding="ascii").strip()
        except OSError:
            return None

    def make_subvolume(self, path: Path) -> None:
        run("btrfs", "subvolume", "create", str(path))

    def clone(self, source: Path, target: Path) -> None:
        """Reuse (D25): a copy that shares the data (btrfs reflink)."""
        run("cp", "-a", "--reflink=always", "--no-target-directory", str(source), str(target))

    def snapshot(self, source: Path, target: Path) -> None:
        run("btrfs", "subvolume", "snapshot", "-r", str(source), str(target))

    def delete_subvolume(self, path: Path) -> None:
        run("btrfs", "property", "set", "-ts", str(path), "ro", "false")
        run("btrfs", "subvolume", "delete", str(path))

    def used_inside(self, bid: str) -> tuple[int, int]:
        st = os.statvfs(mountpoint(bid))
        return (st.f_blocks - st.f_bfree) * st.f_frsize, st.f_bavail * st.f_frsize

    def store_free(self, store: Path) -> int:
        st = os.statvfs(store)
        return st.f_bavail * st.f_frsize

    def remove_box(self, box: Path, bid: str) -> None:
        self.close(bid)
        box.unlink(missing_ok=True)


def new_backup_id() -> str:
    return secrets.token_hex(16)


def host():
    if conf.TEST:
        from fakehost import FakeHost
        return FakeHost()
    return RealHost()


def which(program: str) -> bool:
    return shutil.which(program) is not None
