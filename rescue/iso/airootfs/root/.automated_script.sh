#!/usr/bin/env bash
# The Rescue USB's entry point on tty1 (D47): the wizard, full screen, as
# Omarchy's installer starts its configurator. Other consoles get a shell.
[[ $(tty) == /dev/tty1 ]] || exit 0
# The console font Omarchy's installer uses: Terminus with the logo's half
# blocks (its console-font.py), at the size the kernel picked.
font=/run/omabackups-rescue/console.psf
if [[ ! -s $font ]]; then
  mkdir -p /run/omabackups-rescue
  height=$(showconsolefont -i -C /dev/tty1 2>/dev/null | sed -n 's/^[0-9]*x\([0-9]*\)x[0-9]*$/\1/p')
  terminus=/usr/share/kbd/consolefonts/ter-v16b.psf.gz
  (( ${height:-16} >= 32 )) && terminus=/usr/share/kbd/consolefonts/ter-v32b.psf.gz
  python3 /usr/share/omabackups/rescue/console-font.py "$terminus" "$font" 2>/dev/null || true
fi
setfont -C /dev/tty1 "$font" 2>/dev/null || setfont ter-v24n 2>/dev/null || true
export TERM=linux COLORTERM=truecolor
while true; do
  omabackups rescue-usb wizard && break
  echo
  echo "The rescue stopped. Press Enter to start again (Alt+F2 opens a shell)."
  read -r _
done
