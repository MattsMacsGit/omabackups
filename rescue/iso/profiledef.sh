#!/usr/bin/env bash
# shellcheck disable=SC2034
# The Rescue USB image (D47). Built by build.sh on top of archiso's own base
# recipe (releng), the way Omarchy's ISO is: zstd squashfs (fast to read on
# every boot), BIOS and UEFI boot.

iso_name="omabackups-rescue"
iso_label="OMABACKUPS_RESCUE"
iso_publisher="OmaBackups <https://github.com/MattsMacsGit/omabackups>"
iso_application="OmaBackups Rescue USB"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux' 'uefi.systemd-boot')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '19' '-b' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/root/.gnupg"]="0:0:700"
  ["/etc/omabackups-rescue"]="0:0:700"
)
