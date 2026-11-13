# The Rescue USB

A USB stick that brings your computer back when it won't start, or onto a new
disk. It starts like Omarchy's own installer, asks a few questions, and puts
your system back the way it was at the restore point you pick.

## Making one

On the panel: **Make Rescue USB** (the "No Rescue USB yet" line, or
Settings). A window opens:

1. **Which stick.** Every disk is listed with what's on it now; the one this
   computer runs on is left out. The cursor starts on the USB stick it
   thinks you mean (a Rescue USB already, or any USB stick); check it's the
   right one, since everything on it is erased. A disk that doesn't look
   like a stick (a big or built-in one, like an expansion card) says so.
   Any stick of 4 GB or more.
2. **The rescue system.** Its size is shown first (about 1 GB). It's
   downloaded once and kept; if the download stops, it carries on where it
   stopped. It's checked against its published checksum before anything is
   written: a download that doesn't match is never used.
3. **Writing it.** The window shows how far it is.
4. **Its settings.** A small part of the stick holds where your backup server
   is and the stick's own key. That key can only read your backup: it can't
   change or delete anything, and it can't open your backup by itself, so
   every rescue asks for your backup's password.

One stick at a time: making a new one switches the last one's key off, so a
lost stick can always be cut off.

**Refresh Rescue USB** (Settings) rewrites only the stick's small settings
part, in seconds. When a newer rescue system is out, it offers that too, with
its size.

## Using it

Start the computer from the stick (the boot menu key, often F12, Esc or F2;
on a Mac, hold Option). Pick **OmaBackups Rescue**. Then:

1. **Wi-Fi**, only if there's no network cable.
2. **Finding your backup**: at home it goes straight to your backup server;
   away, it offers to log in to Tailscale (open the link or scan the code on
   your phone).
3. **Your backup's password.**
4. **Which restore point**: each shows the computer's name and its backup
   line (`omarchy-001`), and when. An older line, from a computer you
   migrated from, says `earlier-001`.
5. **Quick or Full Rescue.** Quick brings your system and settings now and
   leaves your folders for later (it's much faster). Full brings everything in
   one go.
6. **Which disk**: every disk, with what's on it, except the stick itself.
   Everything on the one you pick is replaced.
7. **A password for the restored disk**: the one you'll type every time it
   starts. The same as before, if you like.

Then Omarchy's logo fills as it works. At the end it says what to know,
"It's now safe to remove the USB", and offers to restart.

After a Quick Rescue, the panel says **Finish restore**:

1. **Restore my files** opens **Choose what comes back**: the same picker as
   Choose what gets backed up, the other way round. It shows your home
   folder as it is in the restore point, with the same rows, sizes and keys.
   A tick brings it back; the colours say what's here (**blue** comes back,
   **green** already here, **grey** stays in your backup). Press **s** and
   it comes back while you work; a file that's newer here is never
   overwritten.
2. Open it again as often as you like, to bring back more. It remembers your
   last choices.
3. When everything you want is back, press **Back up now**. That finishes
   the restore, and the panel goes back to its everyday page.

From a terminal: `omabackups restore-files <restore point> --pick`.

If the stick says **This Rescue USB's key no longer works**, a newer Rescue
USB was made since (one stick at a time): use the newest stick, or refresh
this one from your computer (Settings › Refresh Rescue USB).

## Good to know

- Unlocking with a fingerprint or TPM chip needs setting up again.
- Secure Boot must be off (or the boot file signed again) for the restored
  disk to start.
- It needs a UEFI computer (almost every computer from the last ten years).
- If the computer doesn't offer the restored disk at start-up, choose the file
  EFI/BOOT/BOOTX64.EFI on it in the firmware's boot menu.
