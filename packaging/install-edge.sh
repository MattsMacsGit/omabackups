#!/bin/bash
# Install OmaBackups from this clone: the package and the panel plugin.
# Until the Omarchy plugin store lists it (D56), and for testing. Asks for
# this computer's password once (pacman).
#
#   git clone https://github.com/MattsMacsGit/omabackups          (main: the latest release)
#   git clone -b edge https://github.com/MattsMacsGit/omabackups  (edge: what's being built)
#   omabackups/packaging/install-edge.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"

"$here/install-package.sh"

echo "Installing the panel plugin..."
plugin="$HOME/.config/omarchy/plugins/omabackups"
mkdir -p "$plugin"
# The whole repo, as the plugin store installs it (D56): the panel's Install it
# builds the package from this copy. Only what git tracks: no build leftovers.
stage="$(mktemp -d)"
git -C "$repo" ls-files -z | rsync -a --from0 --files-from=- "$repo/" "$stage/"
rsync -a --delete "$stage/" "$plugin/"
rm -rf "$stage"
# The running shell only knows plugins it has scanned: without the rescan,
# enable fails with "plugin 'omabackups' is not known" and the widget never
# appears on the bar. Don't hide enable's errors.
omarchy-shell shell rescanPlugins >/dev/null

if ! omarchy-plugin-enable omabackups --section right; then
  echo "Couldn't put OmaBackups on the bar. Try: omarchy-plugin-enable omabackups --section right" >&2
  exit 1
fi
omarchy-restart-shell >/dev/null 2>&1 || true

echo
echo "Done. OmaBackups is on your bar (the clock turning back): click it to start."
