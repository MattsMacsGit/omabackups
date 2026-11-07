# The OmaBackups guide

How to use OmaBackups, one section per feature. OmaBackups is the backup,
rescue and migration tool for Omarchy: automatic backups, restore a file or
the whole system, and move your setup onto a fresh install.

> OmaBackups 2.0 is being built. This guide grows as each part is finished.

## Contents

1. [Install and remove](#install-and-remove)
2. [The panel](#the-panel)
3. [Set up backups to a backup server](#set-up-backups-to-a-backup-server)
4. [Set up backups to a backup disk](#set-up-backups-to-a-backup-disk)
5. [Backing up](#backing-up)
6. [Restore points](#restore-points)
7. [Your changes to Omarchy](#your-changes-to-omarchy)
8. [Start over](#start-over)
9. [The omabackups command](#the-omabackups-command) ([its own page](COMMANDS.md))

## Install and remove

OmaBackups comes in two parts:

- **The OmaBackups plugin**: the panel on your bar, from the Omarchy plugin store.
- **The `omabackups` package**: the part that does the work. The first time
  you open the panel, it offers to install the package for you.

**Remove OmaBackups** in Settings comes with a later version. Until then,
to remove the package by hand:

```
sudo pacman -R omabackups
```

Your settings stay in `~/.config/omabackups/` and the log in
`~/.local/state/omabackups/`, in case you install it again. Delete those two
folders as well if you want nothing left behind. OmaBackups 1.x uses
different names, so the two can sit side by side without touching each other.

## The panel

OmaBackups lives on your bar: its icon is a clock turning back. Click it to
open the panel; a middle-click backs up now. The icon is dimmed until
backups are set up, and turns red when something needs you.

**Before backups are set up**, the panel walks you through it, one step per
screen:

1. **Set up backups** (or **Migrate from another system**, which comes with
   a later version).
2. **Where?** A backup server on the network, or a backup disk plugged in
   here.
3. **The details.** For a server, type its address and your user name
   there. Then a terminal window opens for the passwords and the questions
   SSH asks (see the next two sections for what each one is). The panel
   moves on by itself when it's done.
4. **Your first backup.** **Back up now** opens the file selection first
   (your own files ticked, the trash and caches skipped); saving starts the
   backup. Meanwhile the panel offers a Rescue USB; **Later** leaves a reminder.

**Every day**, the panel shows:

- when your latest backup was, where it goes, and how much room is left;
- a line for anything worth knowing, only while it's true: waiting for a
  known network, can't reach your backup, the last backup failed, automatic
  backups are off, a health check problem, no Rescue USB yet;
- **Back up now**, or, while a backup runs, what it's doing and **Stop**;
- your restore points, newest first (**More…** shows them all).

The gear opens **Settings**: choose what gets backed up, automatic backups,
the health check, away from home, restore points (smart thinning, and the
ones to keep), and your backup (its size and room, its password, Start
over).
Each switch is a real switch; its gear shows only that switch's own options.

**Keys:** **↑↓** move, **Enter** or **Space** press, **→** open a switch's
options, **←** or **⌫** back, **Esc** close. The mouse works too.

## Set up backups to a backup server

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
    and you pick how big your backup can be.
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

## Set up backups to a backup disk

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

OmaBackups backs up on its own every hour (or every day or week: see the
panel's Settings, or [the settings table](COMMANDS.md#settings)). If the
computer was off or asleep when one was due, it runs soon after it wakes up.

Automatic backups only ever follow choices you've backed up yourself. So
after a fresh setup, and each time you save new choices in the picker, they
wait until you press **Back up now** (the panel says "Automatic backups are
off" until then). Your first manual backup switches them on. If you turn
them off yourself, they stay off until your next manual backup.

### Away from home

Backups run wherever you are. OmaBackups finds out by itself whether you're
home: if your backup server answers at its home address, you are. If not, it
reaches the server through [Tailscale](https://tailscale.com) instead, if
both have it (OmaBackups learns the server's Tailscale address while you're
home; there's nothing to set up).

Away from home, backups are compressed, and anything bigger than your limit
(500 MB to start with) asks first. That's for slow or metered connections,
where a big backup counts against your data on both ends. Settings › **Away
from home** sets the limit (its gear), or switches the question off: then
backups never ask, on any network. The question looks like this:

- **Back up now**: `omabackups away answer now`
- **Wait until I'm on a known network**: `omabackups away answer wait`

An automatic backup over the limit simply waits: `omabackups status` shows
"Waiting for a known network", and it runs by itself once you're home.

### When your backup is full

Before sending anything, OmaBackups checks the backup has room. If it
doesn't, smart thinning removes the oldest restore points first (never kept
ones, never the newest); with it off, nothing is deleted. Either way, if it
won't fit, it stops before sending anything and says what to do.

### The nightly health check

Disks wear out, and a damaged file in a backup is worst found on the day you
need it. So every night (at midnight, for two hours, unless you change it in
Settings: `health.on`, `health.at`, `health.minutes`) your backup server
reads part of your backup back and checks every block against the checksum
written with it. Each night carries on where the last stopped, so a big
backup is fully checked over a few nights.

If a backup comes along while the check is running, the check steps aside
and carries on afterwards, so neither slows the other down.

You only hear about it when something's wrong. `omabackups status` then says
either that the disk reported read or write errors (a loose cable or a tired
disk: worth a look), or that damaged files were found. Those are sent again
at the next backup, which compares the contents of every file to do it.

### Choose what gets backed up

```
omabackups pick
```

opens the picker in the terminal (the panel opens it for you from Settings).
It starts with your home folders (folders first, then files, each biggest
first), and **☰ Quick skips** at the bottom:

- The **tick** says what's backed up from the next backup on: **✓** all of
  it, **•** part of it (open it to see what's skipped), no mark: skipped.
- The **colour** says what your backup holds:
  - **green ✓**: in your latest restore point, and stays backed up;
  - **blue ✓**: not in your backup yet: it goes in at the next backup;
  - **yellow** (no tick): not backed up any more, but still in older restore
    points, until thinning removes them (a kept restore point holds on to
    it);
  - **grey** (no tick): in none of your restore points.
- The line at the bottom turns **red** if it all won't fit.
- The line under the list explains the highlighted row in plain words.

Keys: **↑↓** move, **Enter** open a folder, **⌫** back, **Space** tick or
skip, **h** show hidden files too, **s** save and quit, **q** quit (it asks
first if you changed something). The mouse works too.

Any folder can be opened, skipped ones too, so you can see what you're
deciding about. Something inside a skipped folder can't be ticked on its
own: tick the folder.

Hidden files and folders (the ones starting with a dot, mostly settings)
aren't shown unless you press h. They're still backed up; Migrate is what
brings settings over to a new computer.

**Quick skips** are switches for big things you may not need in your
backup, each with its size and a note: Downloads, Caches, Trash, Package
cache, Flatpak apps, Virtual machines & containers, AI models and Game
libraries. Caches, Trash and the Package cache start skipped. The rest of
the system is always backed up: the Rescue USB needs it to bring your
computer back.

After you save, the next backup follows your choices. Anything newly
skipped leaves your backup's working copy, but stays in your older restore
points. Anything newly ticked is backed up, and if your backup already had
it from before, it's reused rather than sent again.

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

**The same data is never sent twice.** A folder you stop skipping, or a file
you brought back from a restore point, is already in your backup: the server
checks it's unchanged (same place, size and date) and reuses its copy, which
takes no time and no extra space. Only what's really different is sent.

If a backup is cut off (the network drops, the computer turns off), the next
one checks every file instead and finishes the job: it only sends what's
still missing.

One snapshot stays on your computer between backups. It's what the next
backup compares against, and it's replaced each time.

## Restore points

Each backup makes a **restore point**: your computer as it was at that
moment. `omabackups points` lists them, newest first.

### Smart thinning

Old restore points are thinned out as they age, so you keep plenty of recent
ones and fewer old ones. Smart thinning keeps:

- every backup from the last 24 hours;
- one a day for the 30 days before that;
- one a week after that, for as long as there's room.

About 100 restore points after a year, backing up hourly. Switched off
(Settings › **Restore points**), nothing is deleted by itself: a full backup
stops and says so. Delete ones you don't need: `omabackups delete <point>`.

### Kept restore points

A **kept** restore point is never thinned or deleted. In the panel: Settings ›
Restore points, and switch on the ones to keep. Or:

```
omabackups keep 001-2026-11-07-1400
omabackups release 001-2026-11-07-1400
```

### Your backup's password

To change it: Settings › Your backup › **Change its password** (a terminal
window opens), or:

```
omabackups password change
```

It asks for the current password, then the new one twice. Everyday backups
aren't affected (this computer has its own key), but from then on the Rescue
USB and Migrate need the new password.

## Your changes to Omarchy

Every backup also notes how this computer differs from a fresh Omarchy, and
keeps that list inside the restore point. There's nothing to do: it takes
about a second, and it's what Migrate uses on a new computer to offer you
everything you had.

```
omabackups changes
```

shows the list as of your latest backup:

- **Apps** you installed (from Arch, the AUR, Flatpak, or tools like mise),
  and web apps you added to the menu. Each one says where its settings are.
- **Settings**: your SSH keys, saved passwords, browser profiles, Wi-Fi and
  Bluetooth, and apps whose settings changed since Omarchy set them up.
- **System tweaks**: files you set up yourself in the system's own places
  (services, commands, driver and kernel settings). Only ones no package
  owns and Omarchy didn't make.
- **Keybindings, bar & theme**: each piece of the desktop that differs from
  a fresh Omarchy: keybindings, screens, the bar, your themes and the one in
  use, menus, automation hooks, bar plugins.
- **Backgrounds** you added, and **Your files**: the folders in your home.

Each item says what it is, why you might want it (or not), and how easy it
would be to get back without it.

## Start over

In the panel: Settings › Your backup › **Start over**. Or:

```
omabackups start-over
```

This computer forgets where it backs up, and goes back to **Set up backups**.
Its own snapshots go too. **Your backup is not deleted**: on the server or
the disk, it's still there with all its restore points. Use this to move to a
different backup location.

## The omabackups command

Everything the panel does is also a command you can type in a terminal:
`omabackups --help` lists them. [The command page](COMMANDS.md) covers
`status`, every setting, what to do when something goes wrong, and `--json`
for scripts.
