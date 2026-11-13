"""Setup's terminal screens, in the style of the Omarchy installer (D31): gum
(an Omarchy dependency) draws each question. Arrow keys pick, Enter answers,
Esc cancels. The answers come back on gum's stdout; it draws on the terminal.

Without gum (a terminal that isn't Omarchy's), plain prompts do the same job.
"""

import getpass
import shutil
import subprocess
import sys

from omabackups.core.errors import OmaError

CANCELLED = "Setup was stopped, so nothing was changed."


def _gum() -> bool:
    return shutil.which("gum") is not None and sys.stdin.isatty()


def say(text: str = "") -> None:
    sys.stderr.write(text + "\n")


def title(text: str, note: str = "") -> None:
    """A step's title, bold, with a dim line under it and room around it."""
    say()
    say(f"\033[1m{text}\033[0m")
    if note:
        for row in note.splitlines():
            say(f"\033[2m{row}\033[0m")
    say()


def _run(args: list[str]) -> str:
    done = subprocess.run(["gum", *args], stdout=subprocess.PIPE)
    if done.returncode != 0:          # Esc or Ctrl+C
        raise OmaError(CANCELLED, code="cancelled")
    return done.stdout.decode("utf-8", "replace").rstrip("\n")


def choose(header: str, options: list[str], selected: int = 0) -> int:
    """One of the options, by its number in the list."""
    if _gum():
        picked = _run(["choose", "--header", header, "--selected", options[selected],
                       "--height", str(min(12, len(options) + 1)), *options])
        return options.index(picked) if picked in options else selected
    say(header)
    for n, option in enumerate(options, 1):
        say(f"  {n}. {option}")
    answer = input(f"Which (number) [{selected + 1}]: ").strip() or str(selected + 1)
    if not answer.isdigit() or not 1 <= int(answer) <= len(options):
        raise OmaError(CANCELLED, code="cancelled")
    return int(answer) - 1


def ask(prompt: str, default: str = "", placeholder: str = "") -> str:
    if _gum():
        args = ["input", "--prompt", f"{prompt}> ", "--value", default]
        if placeholder:
            args += ["--placeholder", placeholder]
        return _run(args).strip()
    shown = f"{prompt} [{default}]: " if default else f"{prompt}: "
    return input(shown).strip() or default


def confirm(prompt: str) -> bool:
    """Yes or no; no unless the answer is yes."""
    if _gum():
        return subprocess.run(["gum", "confirm", "--default=false", prompt]).returncode == 0
    return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")


def secret(prompt: str) -> str:
    if _gum():
        return _run(["input", "--password", "--prompt", f"{prompt}> "])
    return getpass.getpass(f"{prompt}: ")
