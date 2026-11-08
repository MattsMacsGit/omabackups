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

echo "Building and installing the omabackups package..."
(cd "$here" && makepkg -sif --noconfirm)

echo "Installing the panel plugin..."
plugin="$HOME/.config/omarchy/plugins/omabackups"
mkdir -p "$plugin"
rsync -a --delete --exclude '*.pyc' "$repo/manifest.json" "$repo/LICENSE" "$repo/README.md" "$repo/plugin" "$plugin/"
omarchy-plugin-enable omabackups --section right >/dev/null 2>&1 || true
omarchy-restart-shell >/dev/null 2>&1 || true

echo
echo "Done. OmaBackups is on your bar (the clock turning back): click it to start."
