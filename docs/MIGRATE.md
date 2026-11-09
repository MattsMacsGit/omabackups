# Migrate to a new computer

Part of [the OmaBackups guide](GUIDE.md).

Every backup keeps a list of how your computer differs from a fresh Omarchy:
the apps you added, their settings, your keybindings, bar and theme, the
System tweaks you made. **Migrate** reads that list on a new computer (or a
fresh install) and brings over whatever you tick.

## Migrate from another system

On the new computer, install OmaBackups, open the panel and choose **Migrate
from another system**. Then:

1. **Connect to your old computer's backup.** Pick the backup server, type its
   address and your user name there. A terminal window opens for the
   passwords: this computer's (a pop-up), your password on the server twice
   (to log in, then for sudo), then **your backup's own password**: the one
   you chose when you set backups up. That's what proves this computer may
   open your backup; it then gets a key of its own, so you never type it again.
2. **Pick the restore point** to start from. The newest is usually the one.
3. **Choose what comes over.** One page per group: Apps, Settings, System
   tweaks, Keybindings, bar & theme, Backgrounds, Your files. What's
   suggested is already ticked; the line under the list says what the
   highlighted thing is, why you might want it, and how easy it is to get
   back without it. **Space** ticks, **←→** or **Enter** turn the pages, and
   **S** starts, once you've looked at every page (Enter never starts it).
   On Your files, choose whether your folders come back now, in the same run
   (start it and walk away), or later.
4. **Migrate.** If an app whose settings are coming back is open (a
   browser, VS Code, Signal...), it asks you to close it first: those apps
   rewrite their settings when they close, which would undo what came back.
   Then apps install, through Omarchy's own installers (some ask for this
   computer's password); then your settings and System tweaks come back.
   Services you had switched on, like Tailscale or Bluetooth, are put back
   with their settings and switched on again; the network is never cut while
   that happens. Then your files, if you chose now. A report says what came
   over and anything that needs a look.
5. **Omarchy restarts.** "Omarchy will now restart to apply your settings":
   press Enter, or it restarts by itself after 15 seconds. Your logins (the
   keyring), services and desktop only go live after a restart. If your files
   are coming back now, it waits for them first. You start up on your own
   desktop, ready to go.

Your user name on the new computer doesn't have to match the old one: your
settings land in your home folder, whatever it's called, and settings that
named your old home folder (`/home/<old name>`) are changed to the new one.
The report says how many. git's GitHub login is linked again too.

## Finishing

The panel then shows what's left, only while it's true:

- **Restore my files to finish**, if you chose later: your folders come back
  while you work, never overwriting a file that's newer here.
- **Back up now**: the first backup on the new computer.

## The handover

Until that first backup, your old computer still owns the backup: a Migrate
that goes wrong changes nothing. The first backup on the new computer takes
it over:

- it carries on the same backup in a new **backup line**: only what's changed
  since the restore point you started from is stored;
- that restore point is kept as your **Return point**, so you can always go
  back to the old system;
- the old computer can still open its restore points (Browse, bring files
  back), but can't back up there any more.

## Run Migrate again

Left something behind? Settings › Restore points › **Run Migrate again**
brings the chooser back, any time, even long after the handover. Pick the
restore point it's in (the Return point holds the old computer's last state).

From a terminal: `omabackups migrate`.

Migrating from a backup disk (rather than a server) comes with a later
version.
