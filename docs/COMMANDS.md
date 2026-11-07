# The omabackups command

Part of [the OmaBackups guide](GUIDE.md).

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
| `away.on` | Away from home, a big backup asks first; off: it never asks | on |
| `away.limit_mb` | Away from home, a backup bigger than this (in MB) asks first | 500 |
| `thinning.on` | Smart thinning of old restore points; off: they all stay until the backup needs the room | on |
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
