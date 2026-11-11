#!/usr/bin/env bash
# Build the Rescue USB image (D47), as root (archiso needs it):
#
#   sudo rescue/iso/build.sh [--out DIR] [--settings DIR]
#
# Starts from archiso's own base recipe (releng, from the archiso package, so
# none of it lives in this repo), lays this folder's recipe on top, builds the
# omabackups package from this clone into a local repo, takes Omarchy's own
# logo and progress screen from the Omarchy package (as Omarchy's ISO does),
# and runs mkarchiso. --settings (testing only) puts a stick's settings into
# the image itself; a real stick keeps them on its own small part (stage 9c).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
out="$repo/rescue/out"
settings=""
while (($#)); do
  case $1 in
    --out) out=$2; shift 2 ;;
    --settings) settings=$2; shift 2 ;;
    *) echo "usage: sudo $0 [--out DIR] [--settings DIR]" >&2; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Run it with sudo: archiso builds as root." >&2; exit 1; }
if [[ -n $settings ]]; then
  for f in rescue.json server.json ssh_key known_hosts; do
    [[ -f $settings/$f ]] || { echo "No stick settings in $settings (make them: omabackups rescue-usb settings $settings)." >&2; exit 1; }
  done
fi
releng=/usr/share/archiso/configs/releng
[[ -d $releng ]] || { echo "archiso isn't installed (sudo pacman -S archiso)." >&2; exit 1; }
# Omarchy's own screens: an installed Omarchy's, or (on GitHub's build machine,
# rescue/iso/ci-build.sh) the files taken out of Omarchy's packages.
share=${OMARCHY_SHARE:-/usr/share/omarchy}
for f in "$share/logo.txt" "$share/install/provisioning/progress-icon.sh"; do
  [[ -f $f ]] || { echo "Omarchy's $f is missing: build on an Omarchy system." >&2; exit 1; }
done
builder=${SUDO_USER:-}
[[ -n $builder && $builder != root ]] || { echo "Run it with sudo from your own user (makepkg won't run as root)." >&2; exit 1; }

work="$(mktemp -d /var/tmp/omabackups-rescue.XXXXXX)"
trap 'rm -rf "$work"' EXIT
profile="$work/profile"

echo "==> The recipe: archiso's base, then ours"
cp -a "$releng" "$profile"
cp "$here/profiledef.sh" "$here/packages.x86_64" "$profile/"
cp -a "$here/airootfs/." "$profile/airootfs/"
rm -f "$profile/airootfs/etc/motd"
# Omarchy's kernel instead of Arch's (file names in the boot menus).
grep -rl 'vmlinuz-linux\|initramfs-linux' "$profile/syslinux" "$profile/efiboot" "$profile/grub" 2>/dev/null |
  xargs -r sed -i -e 's/vmlinuz-linux\b/vmlinuz-linux-omarchy/g' -e 's/initramfs-linux\.img/initramfs-linux-omarchy.img/g'
# The boot menus say what this is: OmaBackups Rescue, not Arch's installer
# (the first thing anyone sees when they pick the stick).
grep -rl 'Arch Linux' "$profile/syslinux" "$profile/efiboot" "$profile/grub" 2>/dev/null |
  xargs -r sed -i -e 's/Arch Linux install medium/OmaBackups Rescue/g' -e 's/Arch Linux live medium/OmaBackups Rescue/g' \
    -e 's/It allows you to install Arch Linux or perform system maintenance/It brings your computer back from your backup/g' \
    -e 's/MENU TITLE Arch Linux/MENU TITLE OmaBackups Rescue/g' \
    -e 's/OmaBackups Rescue (%ARCH%, \(UEFI\|BIOS\|${archiso_platform}\))/OmaBackups Rescue/g'
# No screen reader on the stick (espeakup): its menu entry would only confuse.
rm -f "$profile"/efiboot/loader/entries/*speech*.conf
# Omarchy's own screens (D47): taken from the Omarchy package, never copied into this repo.
mkdir -p "$profile/airootfs/usr/share/omabackups/rescue"
cp "$share/logo.txt" "$share/install/provisioning/progress-icon.sh" "$profile/airootfs/usr/share/omabackups/rescue/"
# Tailscale runs, so a rescue away from home can log in (D48).
mkdir -p "$profile/airootfs/etc/systemd/system/multi-user.target.wants"
ln -sf /usr/lib/systemd/system/tailscaled.service "$profile/airootfs/etc/systemd/system/multi-user.target.wants/"
if [[ -n $settings ]]; then
  echo "==> Testing: this stick's settings built into the image"
  mkdir -p "$profile/airootfs/etc/omabackups-rescue"
  cp -a "$settings/." "$profile/airootfs/etc/omabackups-rescue/"
fi

echo "==> The omabackups package, from this clone"
mkdir -p "$work/pkgrepo"
chown "$builder" "$work" "$work/pkgrepo"
(cd "$repo/packaging" && sudo -u "$builder" makepkg -fd --noconfirm >/dev/null)
pkg="$(cd "$repo/packaging" && sudo -u "$builder" makepkg --packagelist)"
cp "$pkg" "$work/pkgrepo/"
repo-add -q "$work/pkgrepo/omabackups-local.db.tar.gz" "$work/pkgrepo/$(basename "$pkg")"

echo "==> Package sources: this system's (Omarchy's repo and Arch's), plus the local one"
awk -v local="[omabackups-local]\nSigLevel = Optional TrustAll\nServer = file://$work/pkgrepo\n" '
  /^\[/ && $0 != "[options]" && !done { print local; done = 1 }
  { print }' /etc/pacman.conf >"$profile/pacman.conf"

echo "==> Building (this downloads what isn't here yet, then takes a while)"
mkdir -p "$out"
mkarchiso -v -w "$work/build" -o "$out" "$profile"

echo "==> Checking every program the rescue runs is in the image"
missing=()
while read -r prog; do
  [[ -z $prog || $prog == \#* ]] && continue
  [[ -x $work/build/x86_64/airootfs/usr/bin/$prog ]] || missing+=("$prog")
done <"$here/programs.txt"
if ((${#missing[@]})); then
  rm -f "$out"/*.iso
  echo "Not in the image: ${missing[*]}. Add their packages to rescue/iso/packages.x86_64; no image was kept." >&2
  exit 1
fi
chown -R "$builder" "$out"
ls -la "$out"
