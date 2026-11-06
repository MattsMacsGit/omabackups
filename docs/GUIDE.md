# The OmaBackups guide

How to use OmaBackups, one section per feature. OmaBackups is the backup,
rescue and migration tool for Omarchy: automatic backups, restore a file or
the whole system, and move your setup onto a fresh install.

> OmaBackups 2.0 is being built. This guide grows as each part is finished.

## Contents

1. [Install and remove](#install-and-remove)
2. [The omabackups command](#the-omabackups-command)

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
