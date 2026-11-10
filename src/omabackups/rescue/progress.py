"""The rescue's progress: Omarchy's own traced-logo screen (D47).

Omarchy's progress-icon.sh draws it for the ISO installer and first-boot
setup. It's used as it is (taken from the Omarchy package at build time, as
Omarchy's ISO does): a small bash loop sources it and draws ten frames a
second, and the rescue tells it how far along it is (per mille), with a
status line and a tip. Nothing of its drawing is copied here.
"""

import subprocess
from pathlib import Path

from omabackups.core.errors import OmaError

ICONS = (Path("/usr/share/omabackups/rescue/progress-icon.sh"),
         Path("/usr/share/omarchy/install/provisioning/progress-icon.sh"))

LOOP = r'''
source "$1"
printf '\033[?25l'
trap 'printf "\033[?25h"' EXIT
progress_icon_layout /dev/tty 78
progress_icon_static
pm=0 status="" tip=""
while true; do
  if IFS='|' read -r -t 0.1 a b c; then
    if [[ $a == finish ]]; then progress_icon_finish "$b" "$c"; exit 0; fi
    pm=$a status=$b tip=$c
  elif (( $? <= 128 )); then
    exit 0
  fi
  progress_icon_frame "$pm" "$status" "$tip"
done
'''


def icon_script() -> Path:
    for p in ICONS:
        if p.is_file():
            return p
    raise OmaError("Omarchy's progress screen (progress-icon.sh) isn't on this system.", code="no-progress-icon")


class Progress:
    """Phases, each a share of the whole: show(phase, fraction, status, tip)."""

    def __init__(self, phases: list[tuple[str, float]]):
        total = sum(w for _, w in phases) or 1
        self.start, at = {}, 0.0
        for name, weight in phases:
            self.start[name] = (at, weight / total)
            at += weight / total
        self.proc = subprocess.Popen(["bash", "-c", LOOP, "progress", str(icon_script())],
                                     stdin=subprocess.PIPE, text=True)

    def _send(self, line: str) -> None:
        try:
            self.proc.stdin.write(line.replace("\n", " ") + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def show(self, phase: str, fraction: float, status: str, tip: str = "") -> None:
        begin, share = self.start[phase]
        pm = int(1000 * (begin + share * max(0.0, min(1.0, fraction))))
        self._send(f"{min(pm, 999)}|{status.replace('|', ' ')}|{tip.replace('|', ' ')}")

    def finish(self, status: str, tip: str = "") -> None:
        self._send(f"finish|{status.replace('|', ' ')}|{tip.replace('|', ' ')}")
        self.close()

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except (BrokenPipeError, ValueError):
            pass
        self.proc.wait(timeout=30)
