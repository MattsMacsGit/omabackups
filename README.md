# OmaBackups

The backup, rescue and migration tool for Omarchy, on your bar.

- **Automatic backups** to a small backup server at home (a Raspberry Pi is
  plenty) or a disk you plug in. Encrypted, every hour, and only what changed
  is sent: a backup usually takes seconds. Away from home it carries on through
  Tailscale, and asks first before sending something big.
- **Restore points** you can open and copy from, kept and thinned for you
  (all of the last day, then one a day for a month, then one a week), checked
  every night for damage.
- **A Rescue USB** that brings your computer back when it won't start, or onto
  a new disk. It starts like Omarchy's own installer: pick a restore point,
  Quick or Full Rescue, and watch Omarchy's logo fill. [How it works](docs/RESCUE.md)
- **Migrate** your whole setup onto a fresh Omarchy (even a newer one, even
  with another user name): your apps, settings, logins, keybindings, bar,
  theme and fonts come over and are merged into the new release, not copied
  over it. Then your files. [How it works](docs/MIGRATE.md)
- **Restore my files** brings your folders back while you work. A file that's
  newer on your computer is never overwritten. [Getting things back](docs/RESTORING.md)

Everything is in [the guide](docs/GUIDE.md).

**Version 2.0 is being built.** It's tested on real hardware, but not
released yet.

## Try it before the release

On Omarchy, in a terminal, two commands:

```
git clone -b edge https://github.com/MattsMacsGit/omabackups
```

```
omabackups/packaging/install-edge.sh
```

The first downloads OmaBackups (the `edge` branch, where 2.0 is being built).
The second builds and installs the `omabackups` package, then puts the panel
on your bar: it asks for your computer's password once. Then click the
OmaBackups icon on the bar (a clock turning back) to set up backups, or to
Migrate from another computer.

Licensed under the MIT License (see [LICENSE](LICENSE)).
