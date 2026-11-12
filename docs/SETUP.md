# Setting up backups

Part of the [OmaBackups guide](GUIDE.md).

## To a backup server

A **backup server** is any always-on Linux computer on your network: a
Raspberry Pi, an old laptop, a home server. It needs SSH, systemd, sudo and
Python 3 (Debian, Ubuntu, Raspberry Pi OS, Arch and Fedora all have them).
Other things running on it are left alone.

### What you need

- The server's address on your network (for example `192.168.1.20`).
- Your login on the server (a user name and its password), with sudo.
- A disk on the server with room for your backup. Setup lists every disk
  there, with its size, its free space and what's on it. You pick one, then:
  - **Its free space**: nothing is erased. OmaBackups makes its own folder,
    `omabackups-store`, at the top of the disk, next to what's already there,
    and you pick how big your backup can be: **half** of the free space
    (suggested, since the disk is often shared with other things), **all of
    it**, or a size you type. The size is set once: to change it later, set
    up backups again.
  - **The whole disk**: it's erased and used only for backups. (The disk the
    server runs from is only offered for its free space.)

  Either way, your backup is one encrypted file inside, and it works the
  same. There's no path to type.

### Setting it up

```
omabackups setup server
```

Or from the panel: **Set up backups** › **A backup server on the network**.
It asks for the address and your user name there, where on the server your
backup should go, and three passwords, each once. Pick with the arrow keys
and Enter; Esc stops setup without changing anything. The passwords:

1. **This computer's password** (a pop-up). This links your user to
   OmaBackups, so everyday backups never need a password again.
2. **Your password on the server**, to log in there.
3. **The server's sudo password**, to set up OmaBackups on it.

If the server is new to this computer, SSH first shows its fingerprint and
asks if you trust it: answer `yes` if it's your server.

Then you **choose your backup's password**. Write it down and keep it
somewhere safe. Everyday backups don't need it, because this computer has its
own key. You need it to open your backup from a Rescue USB, or from a new
computer when you Migrate. Without it, nobody can open your backup, not even
you.

### What it sets up on the server

- An account called `omabackups-gate`, which nobody logs in to. Your
  computer's key can only reach OmaBackups' gatekeeper through it: no shell,
  and nothing else on the server.
- The gatekeeper: one small program with a fixed list of jobs. It only lets
  each computer touch its own backup.
- Your backup: an encrypted box in the folder you chose. It's unlocked only
  while a backup or restore is using it, and locks itself again after 10 quiet
  minutes.

Several computers can back up to the same server. Each gets its own box and
its own password, and none of them can see the others.

## To a backup disk

A **backup disk** is a USB disk (or any disk) plugged into this computer.
It's erased and becomes your encrypted backup.

```
omabackups setup disk
```

It lists every disk it can see, with what's on each one: "your computer's
internal drive", "formatted for a Mac", "encrypted: can't see inside", "in
use". Only the disk your system is running from is left out. Read the list
carefully: **the disk you pick is erased**, whatever is on it.

Then it asks for this computer's password once (a pop-up), and you choose
your backup's password, as for a server. Inside, the disk holds exactly what
a server would: the same restore points, the same health check.

When the disk isn't plugged in, backups wait and `omabackups status` says
so. Plug it in and the next one runs by itself.
