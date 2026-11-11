#!/usr/bin/env bash
# Build the Rescue USB image on GitHub's build machine (D16, 9c), inside an
# Arch container: Omarchy's package repo trusted with its own published key
# (rescue/iso/omarchy.gpg, from omacom-io/omarchy-iso's builder/omarchy.gpg:
# 40DF B630 FF42 BCFF B047 046C F013 4EE6 80CA C571), Omarchy's two screen
# files taken out of its packages without installing them, then build.sh.
#
#   docker run --privileged -v "$PWD:/src" -w /src archlinux:latest rescue/iso/ci-build.sh OUT
set -euo pipefail
out=${1:-/src/rescue/out}
here="$(cd "$(dirname "$0")" && pwd)"
OMARCHY_KEY=40DFB630FF42BCFFB047046CF0134EE680CAC571

pacman-key --init
pacman-key --populate archlinux
pacman-key --add "$here/omarchy.gpg"
pacman-key --lsign-key "$OMARCHY_KEY"
printf '\n[omarchy]\nServer = https://pkgs.omarchy.org/stable/$arch\n' >>/etc/pacman.conf
pacman -Syu --noconfirm --needed archiso base-devel sudo

# Omarchy's logo (omarchy-settings) and progress screen (omarchy), as files only.
pacman -Sddw --noconfirm omarchy omarchy-settings
share=/tmp/omarchy-share
mkdir -p "$share"
for pkg in /var/cache/pacman/pkg/omarchy-[0-9]*.pkg.tar.zst /var/cache/pacman/pkg/omarchy-settings-[0-9]*.pkg.tar.zst; do
  bsdtar -xf "$pkg" -C "$share" usr/share/omarchy/logo.txt usr/share/omarchy/install/provisioning/progress-icon.sh 2>/dev/null || true
done

# makepkg won't run as root: a build user, as a person would be.
useradd -m builder 2>/dev/null || true
chown -R builder "$here/../../packaging"
SUDO_USER=builder OMARCHY_SHARE="$share/usr/share/omarchy" "$here/build.sh" --out "$out"
