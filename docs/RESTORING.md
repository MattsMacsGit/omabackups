# Getting things back

Part of [the OmaBackups guide](GUIDE.md).

## Browse a restore point

Every restore point on the panel is a button. Click one (Today 9:02 pm,
say) and it opens in your file manager, whichever one you've set as the
default for folders. You land in your home folder **as it was then**; one
level up are System and Boot.

It's read-only: nothing in a restore point can be changed. To bring something
back (a folder you deleted, an older version of a file), **copy it out** of
that window into your home folder, as you would from a USB stick.

While it's open, the panel says **Browsing Today 9:02 pm · read-only**. Press
**Done** to close it: your backup locks itself again. Backups carry on as
normal while one is open.

From a terminal:

```
omabackups points
omabackups browse 001-2026-11-07-2102
omabackups browse done
```

Opening one from a backup server takes a few seconds; from a backup disk
it's almost instant. Files you couldn't read on the computer itself (other
users' files, some system files) can't be read here either.

## Restore my files

After a Migrate or a Rescue, your system is back but your own files are
still in the restore point. **Restore my files** brings your home folder
back from it. It never overwrites a file that's newer on your computer, so
anything you've changed since stays as it is.

The panel shows how far it's got, with **Stop (carry on later)**: stopped
part-way, it carries on where it left off next time, without sending again
what's already back.

From a terminal:

```
omabackups restore-files 001-2026-11-07-2102
omabackups restore-files stop
```
