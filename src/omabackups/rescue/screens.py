"""The Rescue USB's question screens, drawn the way Omarchy's ISO configurator
draws its own (D47): the green Omarchy logo centred at the top, every widget
lined up under it, grey hints, red problems, the same confirm colours. gum
draws each widget on the terminal; answers come back on its stdout.

The logo is Omarchy's own: on the stick a copy taken from the Omarchy
package at build time, here Omarchy's.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from omabackups.core.errors import OmaError

LOGOS = (Path("/usr/share/omabackups/rescue/logo.txt"), Path("/usr/share/omarchy/logo.txt"))
GREY, RED, GREEN = "8", "1", "2"
STOPPED = "The rescue was stopped. Nothing was changed."
# The configurator's confirm colours (omarchy-iso configs/airootfs/root/configurator).
CONFIRM = {"GUM_CONFIRM_PROMPT_FOREGROUND": "6", "GUM_CONFIRM_SELECTED_FOREGROUND": "0",
           "GUM_CONFIRM_SELECTED_BACKGROUND": "2", "GUM_CONFIRM_UNSELECTED_FOREGROUND": "7",
           "GUM_CONFIRM_UNSELECTED_BACKGROUND": "0"}
QUIET = {"GUM_CHOOSE_SHOW_HELP": "false", "GUM_CONFIRM_SHOW_HELP": "false",
         "GUM_INPUT_SHOW_HELP": "false", "GUM_FILTER_SHOW_HELP": "false"}


def logo() -> str:
    for p in LOGOS:
        if p.is_file():
            return p.read_text().rstrip("\n")
    return "OmaBackups Rescue"


def _width() -> int:
    try:
        return os.get_terminal_size(sys.stderr.fileno()).columns
    except OSError:
        return 80


def _pad() -> int:
    """Left padding that centres the logo; everything lines up with it."""
    widest = max(len(line) for line in logo().splitlines())
    return max(0, (_width() - widest) // 2)


def _env() -> dict:
    pad = f"0 0 0 {_pad()}"
    return {**os.environ, **CONFIRM, **QUIET,
            **{f"GUM_{w}_PADDING": pad for w in ("CHOOSE", "FILTER", "INPUT", "SPIN", "CONFIRM")}}


def _gum(args: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    if not shutil.which("gum"):
        raise OmaError("The rescue screens need gum.", code="no-gum")
    return subprocess.run(["gum", *args], env=_env(), stdout=subprocess.PIPE if capture else None)


def clear_logo() -> None:
    sys.stderr.write("\033[H\033[2J")
    sys.stderr.flush()
    _gum(["style", "--foreground", GREEN, "--padding", f"1 0 0 {_pad()}", logo()], capture=False)


def text_width() -> int:
    """Body text is as wide as the logo above it (and never past the screen's
    edge): a long line wraps inside that column, as the installer's does. With
    no width, it ran to the edge and wrapped back to the far left."""
    widest = max(len(line) for line in logo().splitlines())
    return max(20, min(widest, _width() - _pad() - 1))


def say(text: str = "", colour: str = "") -> None:
    pad = _pad()
    args = ["style", "--padding", f"0 0 0 {pad}", "--width", str(pad + text_width())] + \
        (["--foreground", colour] if colour else []) + [text or " "]
    _gum(args, capture=False)


def gap() -> None:
    sys.stderr.write("\n")
    sys.stderr.flush()


def step(text: str, hint: str = "") -> None:
    """A fresh screen: the logo, a line, and a grey hint under it."""
    clear_logo()
    gap()
    say(text)
    if hint:
        say(hint, GREY)
    gap()


def _answer(done: subprocess.CompletedProcess) -> str:
    if done.returncode != 0:            # Esc or Ctrl+C
        raise OmaError(STOPPED, code="cancelled")
    return done.stdout.decode("utf-8", "replace").rstrip("\n")


def choose(header: str, options: list[str], selected: int = 0) -> int:
    picked = _answer(_gum(["choose", "--height", str(min(12, len(options) + 1)), "--header", header,
                           "--selected", options[selected].replace(",", "\\,"), *options]))
    return options.index(picked) if picked in options else selected


def ask(prompt: str, placeholder: str = "", value: str = "") -> str:
    return _answer(_gum(["input", "--prompt.foreground", "#845DF9", "--prompt", f"{prompt}> ",
                         "--placeholder", placeholder, "--value", value])).strip()


def secret(prompt: str, placeholder: str = "") -> str:
    return _answer(_gum(["input", "--password", "--prompt.foreground", "#845DF9", "--prompt", f"{prompt}> ",
                         "--placeholder", placeholder]))


def confirm(question: str, yes: str, no: str) -> bool:
    done = _gum(["confirm", "--affirmative", yes, "--negative", no, question])
    if done.returncode in (0, 1):
        return done.returncode == 0
    raise OmaError(STOPPED, code="cancelled")


def wait(title: str, seconds: float) -> None:
    """The configurator's notice: a spinner with one line, for a moment."""
    _gum(["spin", "--spinner", "pulse", "--title", title, "--", "sleep", str(seconds)], capture=False)
