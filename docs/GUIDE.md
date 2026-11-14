# The OmaBackups guide

How to use OmaBackups, one section per feature. OmaBackups is the backup,
rescue and migration tool for Omarchy: automatic backups, restore a file or
the whole system, and move your setup onto a fresh install.

> OmaBackups 2.0 is being built. This guide grows as each part is finished.

## Contents

1. [Install and remove](#install-and-remove)
2. [The panel](#the-panel)
3. [Set up backups](#set-up-backups) (to a server or a disk: [its own page](SETUP.md))
4. [Backing up](#backing-up)
5. [Restore points](#restore-points) (and [getting things back](RESTORING.md))
6. [Your changes to Omarchy](#your-changes-to-omarchy) (and [Migrate](MIGRATE.md))
7. [The Rescue USB](RESCUE.md): bring your computer back when it won't start
8. [Start over](#start-over)
9. [The omabackups command](#the-omabackups-command) ([its own page](COMMANDS.md))

## Install and remove

OmaBackups comes in two parts:

- **The OmaBackups plugin**: the panel on your bar, from the Omarchy plugin store.
- **The `omabackups` package**: the part that does the work. The first time
  you open the panel, it offers to install the package for you.

Plugged in, OmaBackups' backup disks and the Rescue USB are listed in your
file manager but never opened on their own: OmaBackups opens them when it
needs them.

**Remove OmaBackups** (Settings › Your backup, or `omabackups remove`)
takes away its services, snapshots and settings, and asks whether to delete
your backup too (twice, because that can't be undone). Then remove the
package:

```
sudo pacman -R omabackups
``` OmaBackups 1.x uses
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
- **Back up now** (**Resume backup** after a backup was stopped or cut off),
  or, while a backup runs, what it's doing, how far it's got, and **Stop**;
- your restore points, newest first: click one to open it (**More…**: all).

The gear opens **Settings**: choose what gets backed up, automatic backups,
the health check, away from home, restore points (smart thinning, and the
ones to keep), and your backup (its size and room, its password, Start
over).
Each switch is a real switch; its gear shows only that switch's own options.

**Keys:** **↑↓** move, **Enter** or **Space** press, **→** open a switch's
options, **←** or **⌫** back, **Esc** close. The mouse works too.

## Set up backups

Backups go to a **backup server** (a small computer such as a Raspberry Pi,
reached at home and, through Tailscale, away) or a **backup disk** you plug in.
How to set up each: [Setting up backups](SETUP.md).

## Backing up

### Back up now

```
omabackups backup
```

It shows what it's doing, then the name of the new **restore point**, for
example `001-2026-11-07-1400` (backup line 001, 7 November 2026, 2:00 pm).

**How far it's got.** Each part (system, home, boot) shows its own step:
first "Checking home…", then "Backing up home…" with a bar. The bar is
honest: it measures what this backup really has to send, worked out before
the copy starts, so it never jumps back or stops short. Under it: how much
is sent of how much, the speed over the last minute, and the time left
once it can be trusted (after a few minutes of steady sending). While it's
still checking, a line sweeps back and forth, because the total isn't known
yet.

**Stuck.** If nothing moves for 3 minutes (no data sent, no file finished),
the backup stops by itself and says so. The panel warns from the first
minute. An automatic backup tries again at the next one; your first backup
waits for you to press **Resume backup**. A computer that's asleep isn't
stuck: the 3 minutes only count while it's awake.

**Stop and Resume backup.** `omabackups stop` (or **Stop** on the panel)
stops a backup that's running. Nothing is lost: **Resume backup** (or
`omabackups backup`) carries on from where it got to.

### Automatic backups

OmaBackups backs up on its own every hour (or every day or week: see the
panel's Settings, or [the settings table](COMMANDS.md#settings)). If the
computer was off or asleep when one was due, it runs soon after it wakes up.

Automatic backups only ever follow choices you've backed up yourself. So
after a fresh setup, and each time you save new choices in the picker, they
wait until you press **Back up now** (the panel says "Automatic backups are
off" until then). Your first manual backup switches them on. If you turn
them off yourself, they stay off until your next manual backup.

On battery under 20% (not plugged in), automatic backups and the health
check wait; one you start yourself always runs. When your backup can't be
reached, they skip quietly and try again next time. A notification (at most
once a day) says when backups are paused after a rescue, when there's been
no backup for three of their times in a row, when your backup is nearly
full, and when the health check finds damage.

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
still won't fit, it stops before sending anything and says so: "This won't
fit on your backup location", with how much it needs and how much is free.
Then remove some files from what gets backed up (the line opens **Choose
what gets backed up**), or pick a new disk for your backup (set up backups
again). A full backup first clears what you've removed or skipped, so that
room counts.

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
disk: worth a look), or that damaged files were found. The next backup sends
each damaged file again, whole, from this computer (one that's no longer
here is noted), and never reuses a damaged copy. Damage found twice within
three months means the disk itself may be failing.

### Choose what gets backed up

```
omabackups pick
```

opens the picker in the terminal (the panel opens it for you from Settings).
It opens on **Quick skips**: switches for big things, each with its size.
Most people switch off one or two (Downloads, say) and save. The last row,
**Your files**, opens your home folders, all ticked (folders first, then
files, each biggest on your computer first, so nothing moves when you tick
or untick it), to skip anything else:

- The **tick** says what's backed up from the next backup on: **✓** all of
  it, **•** part of it (open it to see what's skipped), no mark: skipped.
  Hidden things the Quick skips leave out everywhere (like `.cache`
  folders) don't count towards **•**: they're explained under Quick skips.
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

A switch only covers the big part you can get again, never a program's
settings, logins or saves: Game libraries skips Steam's installed games
(Steam itself, your login and your Proton saves stay backed up), and
Virtual machines & containers skips disk images, container storage and
Bottles' downloadable runners (each bottle, with your Windows apps and
their saves, stays backed up).

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

**A full backup checks once, then knows.** The first backup (and any full
one) starts by asking the backup server what it's missing: a few minutes,
however much there is. That list is kept on your computer, and each file is
ticked off as it arrives. If the backup is cut off (the network drops, the
battery goes flat, you press Stop), the next one doesn't ask the server
again: your disk says what changed since, and it carries on with what's
still unticked plus those changes. The list is deleted when the backup
finishes. If an everyday backup is cut off, the next one checks once and
finishes the job.

One snapshot stays on your computer between backups. It's what the next
backup compares against, and it's replaced each time. An unfinished full
backup keeps its own snapshot until it's done.

## Restore points

Each backup makes a **restore point**: your computer as it was then. To look
inside one or bring files back, see [Getting things back](RESTORING.md).

### Smart thinning

Old restore points are thinned out as they age, so you keep plenty of recent
ones and fewer old ones. Smart thinning keeps:

- every backup from the last 24 hours;
- one a day for the 30 days before that;
- one a week after that, for as long as there's room.

About 100 restore points after a year, backing up hourly. Off (Settings ›
**Restore points**), nothing is deleted by itself: a full backup stops and
says so. To delete one yourself, see below.

### Kept restore points

A **kept** restore point is never thinned, and nothing deletes it by itself.
In the panel: Settings › Restore points, and switch on the ones to keep. Or:

```
omabackups keep 001-2026-11-07-1400
omabackups release 001-2026-11-07-1400
```

Each kept restore point says why:

- **★ kept**: you kept it.
- **★ kept restore**: a Rescue USB restored from it. It's kept from the
  moment you pick it on the stick. Once everything came back and a backup
  ran, it lets go by itself; after a **Back up anyway** it stays kept,
  because it holds what didn't come back. Only `omabackups delete` removes
  it before then.
- **★ kept migrate**: the Return point, where a Migrate's handover started.

### Deleting a restore point

Any restore point can be deleted from a terminal, the newest and kept ones
too. It asks first, and it can't be undone:

```
omabackups delete 001-2026-11-07-1400
```

The panel never deletes a restore point you didn't choose to lose.

### Rebuilding the working copy

If your backup's working copy ever goes wrong, `omabackups rebuild-from`
rebuilds it from a restore point you trust: see
[Getting things back](RESTORING.md#rebuilding-the-working-copy).

### Your backup's password

Settings › Your backup › **Change its password**, or see
[the command page](COMMANDS.md#your-backups-password).

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
