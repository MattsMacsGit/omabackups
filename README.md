# OmaBackups

The backup, rescue and migration tool for Omarchy: automatic backups, restore
a file or the whole system, and move your setup onto a fresh install.

**Version 2.0 is being built.** See [the guide](docs/GUIDE.md).

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
