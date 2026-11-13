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
3. **Choose what comes over.** One page per group: **Logins & keys** (SSH
   and GPG keys, saved passwords, Wi-Fi, Bluetooth, GitHub...), **Apps** (with
   their settings), **Your desktop** (keybindings, bar, theme, and the extras:
   your fonts, icons and cursors, default apps, file manager bookmarks,
   desktop settings, your own app launchers and the apps you start at
   login), **Backgrounds**, **Terminal & automation** (your shell and its
   history, your scripts, your own services and scheduled jobs), **System
   tweaks**, **Your files**. What's
   suggested is already ticked, and that includes everything that holds your
   own settings or history: your terminal setup and command history, and the
   settings of each app you changed, terminal apps too. Untick what you'd
   rather start fresh. The line under the list says what the
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

## Keybindings, bar & theme

These are merged, never copied: a new Omarchy release comes with its own
versions of these files, and copying the old ones over would throw away
what's new (or break it). Each part is its own tick on that page:

- **Key bindings** and the other Hyprland files (keyboard and mouse, window
  rules, look and feel, apps started at login): this Omarchy's file stays,
  and your own lines are added to it. "Your own" means what you changed from
  the file *your* Omarchy release came with, whichever release that was. A
  setting that's a list (like keyboard options) keeps this release's values
  and adds yours. A change that no longer fits is listed in the report to
  add by hand, never forced in. If Hyprland doesn't accept the result, the
  file is put back as it was and your version kept beside it
  (`*.from-old-system`).
- **Bar layout**: your bar and its widgets; new parts of this release (like
  the dock) stay. **Each bar plugin** is its own tick: one you leave out is
  left off the bar too, and Run Migrate again brings it later.
- **Theme**: the theme you used is set again through Omarchy, with its
  background. Your own themes have their own ticks.
- **Screen setup** is "up to you": a new computer may have another screen.
- **Hooks** (scripts Omarchy runs on every update, or when the theme
  changes) are listed one by one: check them first.

You can also start with a clean Omarchy, try its defaults, and bring over
what you miss later with Run Migrate again.

Your user name on the new computer doesn't have to match the old one: your
settings land in your home folder, whatever it's called, and settings that
named your old home folder (`/home/<old name>`) are changed to the new one.
The report says how many. git's GitHub login is linked again too.
Apps that sync folders (Nextcloud, Syncthing...) are the exception: they keep
their old folder paths until **Restore my files** has brought your folders
back, so they never start again from scratch on empty folders. Then they're
pointed at the folders here; if one was running it's closed for that, and the
panel says to start it again.

## What Migrate tells you at the end

The report lists what came over and anything that needs a look. Before it
ends, Migrate checks that each thing you ticked is really here now; anything
that isn't is listed as **Didn't come over**, so nothing goes missing
quietly. Run Migrate again to try once more, or copy it out with Browse.

If Migrate replaced a setting that was already here and different, the one
that was here is kept first, in a dated folder with the same paths:
`~/.local/state/omabackups/replaced/` (and System tweaks in
`/var/lib/omabackups/replaced/`, readable by root only). The report says
where. So any Migrate can be undone by hand.

Picking a restore point older than the one you migrated from? The chooser
says so at the top: what you tick then replaces newer settings.

## Finishing

The panel then shows what's left, only while it's true:

- **Restore my files to finish**, if you chose later: your folders come back
  while you work, never overwriting a file that's newer here. If a folder
  already has things in it here (a working copy of a project, say), the panel
  names it first: old files would be added beside what's there, so move a
  working copy aside before bringing it back. Migrate asks the same before
  bringing your files back in the same run.
- **Back up now**: the first backup on the new computer. While folders you
  chose are still on the backup, it waits (**Paused until your files are
  back**), as after a Quick Rescue: hold **Ctrl** and click it to back up
  anyway ([the Rescue USB guide](RESCUE.md#backups-wait-for-your-folders)
  says what that means).

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

Whatever is here already shows in green as **Already in**, with no tick
box: what an earlier Migrate from that old computer brought over, apps that
are installed, and settings that are here as they are in the backup (it
looks first; nothing is copied for that). It's never brought over twice, so
your keybindings and bar don't get doubled. The same goes for folders
already brought back. Settings you've changed since show as normal rows.
Two things count as in even though they keep changing: an app you log in to
(Tailscale), once it's installed and logged in, and your terminal history,
once it has your old commands in it. Only the rest can be ticked. To get a part
back as it was in the backup anyway, open the restore point (Browse) and
copy it out.

If your user name is different on the new computer, settings that name your
old home folder are pointed at the new one, and so are folders an app named
after it (for example, an app that keeps its history per project folder).

From a terminal: `omabackups migrate`.

Migrating from a backup disk (rather than a server) comes with a later
version.
