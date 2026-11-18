#!/bin/bash
# Build and install the omabackups package from the copy of the repo this
# script sits in (D56). The panel's "Install it" runs it from the plugin's
# own folder (the plugin store installs the whole repo), and install-edge.sh
# runs it from a clone. The code that runs as root is exactly this copy;
# the dependencies come from Arch's official repositories.
# Asks for this computer's password once (pacman).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"

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

# Build without sudo (-d: building needs only python, always there), in a
# folder of its own: nothing is written into this copy. Then one pacman -U
# installs the package and fetches its dependencies with it: one password.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
echo "Building the omabackups package..."
(cd "$here" && BUILDDIR="$work" PKGDEST="$work" makepkg -fd --noconfirm)
pkg="$(cd "$here" && PKGDEST="$work" makepkg --packagelist)"
echo "Installing it (asks for this computer's password)..."
sudo pacman -U --noconfirm "$pkg"

# udiskie leaves OmaBackups' disks and the Rescue USB alone when they're plugged in (audit 7.4).
omabackups desktop-rules install || true
echo
echo "The omabackups package is installed."
