#!/usr/bin/env bash
# The Rescue USB's entry point on tty1 (D47): the wizard, full screen, as
# Omarchy's installer starts its configurator. Other consoles get a shell.
[[ $(tty) == /dev/tty1 ]] || exit 0
setfont ter-v24n 2>/dev/null || true
export TERM=linux COLORTERM=truecolor
while true; do
  omabackups rescue-usb wizard && break
  echo
  echo "The rescue stopped. Press Enter to start again (Alt+F2 opens a shell)."
  read -r _
done
