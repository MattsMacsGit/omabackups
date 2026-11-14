#!/bin/bash
# Install OmaBackups from this clone: the package and the panel plugin.
# For testing before the release (then it comes from the AUR and the
# Omarchy plugin store). Asks for this computer's password once (pacman).
#
#   git clone -b edge https://github.com/MattsMacsGit/omabackups
#   omabackups/packaging/install-edge.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"

# A fresh Omarchy install (from the offline ISO) has never downloaded the
# package lists for core/extra, so pacman can't find dependencies like sshfs
# ("database file for 'extra' does not exist" / "target not found: sshfs").
# Update the system first, through `omarchy update`: Omarchy's pacman hook
# refuses a direct `pacman -Syu` ("Woah partner..."), and plain -Sy then
# installing would be a partial upgrade.
for db in core extra; do
  if [ ! -s "/var/lib/pacman/sync/$db.db" ]; then
    echo "Pacman's package lists are missing (fresh install): running omarchy update first..."
    omarchy-update -y
    break
  fi
done

# Build without sudo (-d: building needs only python, always there), then one
# pacman -U installs the package and fetches its dependencies with it: one
# password. makepkg -si asked once for the dependencies and again for the
# package, each through its own sudo.
echo "Building the omabackups package..."
(cd "$here" && makepkg -fd --noconfirm)
pkg="$(cd "$here" && makepkg --packagelist)"
echo "Installing it (asks for this computer's password)..."
sudo pacman -U --noconfirm "$pkg"

echo "Installing the panel plugin..."
plugin="$HOME/.config/omarchy/plugins/omabackups"
mkdir -p "$plugin"
rsync -a --delete --exclude '*.pyc' "$repo/manifest.json" "$repo/LICENSE" "$repo/README.md" "$repo/plugin" "$plugin/"
# The running shell only knows plugins it has scanned: without the rescan,
# enable fails with "plugin 'omabackups' is not known" and the widget never
# appears on the bar. Don't hide enable's errors.
omarchy-shell shell rescanPlugins >/dev/null
# udiskie leaves OmaBackups' disks and the Rescue USB alone when they're plugged in (audit 7.4).
omabackups desktop-rules install || true

if ! omarchy-plugin-enable omabackups --section right; then
  echo "Couldn't put OmaBackups on the bar. Try: omarchy-plugin-enable omabackups --section right" >&2
  exit 1
fi
omarchy-restart-shell >/dev/null 2>&1 || true

echo
echo "Done. OmaBackups is on your bar (the clock turning back): click it to start."
