"""Install the gatekeeper on this server (run once as root by `omabackups
setup server`, through the server login's sudo; D20: no curl, no sudoers).

  gate.pyz install STORE SYSTEM LABEL SHA256 PUBKEY-FILE     (STORE "-": update, keep the store)

(Run with a terminal attached, so sudo can ask for its password.)

Idempotent: running it again updates the gatekeeper and keeps everything else.
Only ever creates OmaBackups' own things: the omabackups-gate account, its
units, /usr/lib/omabackups-gate, /etc and /var/lib/omabackups-gate, and the
backup store folder. Other apps on the server are left alone.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import admin
import conf
import registry
from registry import Refused

UNITS = {
    "omabackups-gate.socket": f"""[Unit]
Description=OmaBackups gatekeeper socket

[Socket]
ListenStream={conf.SOCKET}
SocketUser=root
SocketGroup={conf.ACCOUNT}
SocketMode=0660
DirectoryMode=0755
Accept=yes

[Install]
WantedBy=sockets.target
""",
    "omabackups-gate@.service": f"""[Unit]
Description=OmaBackups gatekeeper (one request)

[Service]
ExecStart=/usr/bin/python3 {conf.INSTALLED} serve
StandardInput=socket
StandardOutput=journal
StandardError=journal
""",
    "omabackups-gate-sweep.service": f"""[Unit]
Description=OmaBackups: lock backups nobody is using

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {conf.INSTALLED} sweep
""",
    "omabackups-gate-sweep.timer": """[Unit]
Description=OmaBackups: lock backups nobody is using, every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=10s

[Install]
WantedBy=timers.target
""",
}

NEEDED = {"cryptsetup": "cryptsetup", "mkfs.btrfs": "btrfs-progs", "btrfs": "btrfs-progs"}
PACKAGE_MANAGERS = (
    ("apt-get", ["apt-get", "install", "-y", "--no-install-recommends"], {"cryptsetup": "cryptsetup-bin"}),
    ("pacman", ["pacman", "-S", "--needed", "--noconfirm"], {}),
    ("dnf", ["dnf", "install", "-y"], {}),
)


def say(text: str) -> None:
    sys.stderr.write(f"  {text}\n")
    sys.stderr.flush()


def run(*cmd: str) -> None:
    done = subprocess.run(list(cmd), stdout=sys.stderr, stderr=sys.stderr)
    if done.returncode != 0:
        raise Refused(f"'{' '.join(cmd)}' failed (exit {done.returncode})")


def install_programs() -> None:
    missing = sorted({pkg for prog, pkg in NEEDED.items() if not shutil.which(prog)})
    if not missing:
        return
    for manager, command, renames in PACKAGE_MANAGERS:
        if shutil.which(manager):
            names = [renames.get(p, p) for p in missing]
            say(f"Installing {', '.join(names)} with {manager}...")
            if manager == "apt-get":
                run("apt-get", "update")
            run(*command, *names)
            break
    else:
        raise Refused(f"this server needs {', '.join(missing)}, and has no package manager "
                      "OmaBackups knows (apt, pacman or dnf). Install them, then run setup again.")
    still = sorted(p for p in NEEDED if not shutil.which(p))
    if still:
        raise Refused(f"{', '.join(still)} still missing after installing")


def make_account() -> None:
    try:
        import pwd
        pwd.getpwnam(conf.ACCOUNT)
    except KeyError:
        say(f"Creating the {conf.ACCOUNT} account...")
        run("useradd", "--system", "--user-group", "--home-dir", str(conf.HOME),
            "--no-create-home", "--shell", "/bin/sh", conf.ACCOUNT)
    # "*": no password can ever log in, but key logins work (a "!" can block them).
    run("usermod", "-p", "*", conf.ACCOUNT)
    for folder in (conf.HOME, conf.HOME / ".ssh"):
        folder.mkdir(parents=True, exist_ok=True)
        os.chown(folder, 0, 0)        # root-owned: the account can't change its own keys
        os.chmod(folder, 0o755)


def place_gatekeeper(me: Path) -> None:
    conf.INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    tmp = conf.INSTALLED.with_name(".gate.pyz.new")
    shutil.copyfile(me, tmp)
    os.chmod(tmp, 0o644)
    os.replace(tmp, conf.INSTALLED)


def place_units() -> None:
    for name, text in UNITS.items():
        path = Path("/etc/systemd/system") / name
        path.write_text(text, encoding="utf-8")
        os.chmod(path, 0o644)
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "omabackups-gate.socket", "omabackups-gate-sweep.timer")


def ssh_warnings() -> list[str]:
    """Say (never change) if the server's SSH setup would keep the account out."""
    done = subprocess.run(["sshd", "-T"], capture_output=True, text=True)
    warnings = []
    for line in done.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "allowusers" and conf.ACCOUNT not in value.split():
            warnings.append(f"SSH only lets in some users (AllowUsers); add {conf.ACCOUNT} there")
        if key == "allowgroups" and conf.ACCOUNT not in value.split():
            warnings.append(f"SSH only lets in some groups (AllowGroups); add {conf.ACCOUNT} there")
        if key == "pubkeyauthentication" and value == "no":
            warnings.append("SSH key logins are switched off (PubkeyAuthentication no)")
    return warnings


def main(argv: list[str]) -> int:
    if os.geteuid() != 0:
        sys.stderr.write("omabackups-gate install: run as root\n")
        return 1
    if len(argv) != 5:
        sys.stderr.write(__doc__)
        return 2
    store, system, label, sha, pubfile = argv
    me = Path(sys.argv[0]).resolve()
    try:
        if hashlib.sha256(me.read_bytes()).hexdigest() != sha:
            raise Refused("the gatekeeper didn't arrive intact (its checksum is wrong); run setup again")
        if not Path("/run/systemd/system").is_dir():
            raise Refused("this server doesn't run systemd, which OmaBackups needs")
        pub = Path(pubfile).read_text(encoding="ascii")[:conf.MAX_SECRET]
        install_programs()
        make_account()
        place_gatekeeper(me)
        if store != "-":          # "-": an update; keep the store as it is
            admin.init(store)
        elif not conf.SETTINGS.exists():
            raise Refused("there's no backup store on this server to keep; set it up first")
        with registry.changing() as data:
            kid = registry.add_key(data, pub, "computer", label, system=system)
        os.chown(conf.AUTHORIZED_KEYS, 0, 0)
        place_units()
        result = {"key": kid, "store": store, "gate": conf.VERSION, "warnings": ssh_warnings()}
    except Refused as exc:
        sys.stderr.write(f"omabackups-gate: {exc}\n")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
