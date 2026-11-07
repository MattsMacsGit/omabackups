# The OmaBackups guide

How to use OmaBackups, one section per feature. OmaBackups is the backup,
rescue and migration tool for Omarchy: automatic backups, restore a file or
the whole system, and move your setup onto a fresh install.

> OmaBackups 2.0 is being built. This guide grows as each part is finished.

## Contents

1. [Install and remove](#install-and-remove)
2. [Set up backups to a backup server](#set-up-backups-to-a-backup-server)
3. [Backing up](#backing-up)
4. [The omabackups command](#the-omabackups-command)

## Install and remove

OmaBackups comes in two parts:

- **The OmaBackups plugin**: the panel on your bar, from the Omarchy plugin store.
- **The `omabackups` package**: the part that does the work. The first time
  you open the panel, it offers to install the package for you.

To remove OmaBackups, use **Remove OmaBackups** in Settings. To remove only
the package by hand:

```
sudo pacman -R omabackups
```

Your settings stay in `~/.config/omabackups/` and the log in
`~/.local/state/omabackups/`, in case you install it again. Delete those two
folders as well if you want nothing left behind. OmaBackups 1.x uses
different names, so the two can sit side by side without touching each other.

## Set up backups to a backup server

A **backup server** is any always-on Linux computer on your network: a
Raspberry Pi, an old laptop, a home server. It needs SSH, systemd, sudo and
Python 3 (Debian, Ubuntu, Raspberry Pi OS, Arch and Fedora all have them).
Other things running on it are left alone.

### What you need

- The server's address on your network (for example `192.168.1.20`).
- Your login on the server (a user name and its password), with sudo.
- A folder on one of the server's disks with room for your backup, for
  example `/srv/backups/omabackups`. OmaBackups keeps your backup there as one
  encrypted file of the size you choose.

### Setting it up

```
omabackups setup server
```

It asks for the address, your user name there, the folder and the size, and
then for three passwords, each once:

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

## Backing up

### Back up now

```
omabackups backup
```

It shows what it's doing, then the name of the new **restore point**, for
example `001-2026-11-07-1400` (backup line 001, 7 November 2026, 2:00 pm).
`omabackups stop` stops a backup that's running. Nothing is lost: the next
backup picks up where it stopped.

### Automatic backups

Once set up, OmaBackups backs up on its own every hour (or every day or week:
see Settings below). If the computer was off or asleep when one was due, it
runs soon after it wakes up.

### Away from home

Backups run wherever you are. OmaBackups finds out by itself whether you're
home: if your backup server answers at its home address, you are. If not, it
reaches the server through [Tailscale](https://tailscale.com) instead, if
both have it (OmaBackups learns the server's Tailscale address while you're
home; there's nothing to set up).

Away from home, backups are compressed, and anything bigger than your limit
(500 MB to start with, see `away.limit_mb` in Settings) asks first, because
it counts against your data on both ends:

- **Back up now**: `omabackups away answer now`
- **Wait until I'm on a known network**: `omabackups away answer wait`

An automatic backup over the limit simply waits: `omabackups status` shows
"Waiting for a known network", and it runs by itself once you're home.

### When your backup is full

Before sending anything, OmaBackups checks the backup has room. If it
doesn't, the oldest restore points go first (never kept ones, never the
newest). If it still won't fit, it stops before sending anything and says
so: make your backup bigger, or skip big folders you don't need.

### The nightly health check

Disks wear out, and a damaged file in a backup is worst found on the day you
need it. So every night (at midnight, for two hours, unless you change it in
Settings: `health.on`, `health.at`, `health.minutes`) your backup server
reads part of your backup back and checks every block against the checksum
written with it. Each night carries on where the last stopped, so a big
backup is fully checked over a few nights.

You only hear about it when something's wrong. `omabackups status` then says
either that the disk reported read or write errors (a loose cable or a tired
disk: worth a look), or that damaged files were found. Those are sent again
at the next backup, which compares the contents of every file to do it.

### What gets backed up

- **System**: everything on your system disk, except temporary files, the
  package cache, crash dumps and other things that are no use after a
  restore.
- **Home**: every user's home folder, except caches, thumbnails and the
  trash.
- **Boot**: the boot partition.

OmaBackups reads your files from a snapshot taken at the start of each
backup, so everything in one restore point is from the same moment, even
while you keep working.

### Why most backups take seconds

The first backup copies everything, so it takes a while. After that, your
disk already knows what changed since the last backup, so OmaBackups sends
only that:

- a renamed or moved folder is moved on the server too, and nothing is sent;
- a big file that changed a little (a virtual machine's disk, say) only
  sends the parts that changed;
- everything else that changed is sent as it is.

If a backup is cut off (the network drops, the computer turns off), the next
one checks every file instead and finishes the job: it only sends what's
still missing.

One snapshot stays on your computer between backups. It's what the next
backup compares against, and it's replaced each time.

## The omabackups command

Everything the panel does is also a command you can type in a terminal. To see
the list:

```
omabackups --help
```

### Where am I up to?

```
omabackups status
```

This tells you where OmaBackups is up to on this computer. On a new install
it says OmaBackups is not set up yet: open the panel and choose
**Set up backups**, or **Migrate from another system**.

### Settings

```
omabackups settings get
omabackups settings set automatic.every daily
```

| Setting | What it does | Default |
|---|---|---|
| `automatic.on` | Automatic backups, on or off | on |
| `automatic.every` | How often: `hourly`, `daily` or `weekly` | hourly |
| `away.limit_mb` | Away from home, a backup bigger than this (in MB) asks first | 500 |
| `health.on` | The nightly health check of your backup | on |
| `health.at` | The hour it starts (0-23) | 0 (midnight) |
| `health.minutes` | How long it runs each night: 30, 60, 120, 240 or 480 | 120 |

### When something goes wrong

Every problem OmaBackups reports says what happened, what to do, and then
**Details to copy**: paste those into a bug report or a message asking for help.
The full log is in `~/.local/state/omabackups/logs/omabackups.log`.

### For scripts

Add `--json` before the command (`omabackups --json status`) and every answer
comes back as one line of JSON.
