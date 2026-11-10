"""Command-line tools from installers other than pacman (1.x's idea), and
your own scripts in ~/.local/bin."""

import json
import os
import subprocess
from pathlib import Path

from omabackups.audit.model import item

CARGO_OWN = {"cargo", "rustc", "rustup", "rustdoc", "rust-gdb", "rust-lldb", "rustfmt", "cargo-fmt",
             "clippy-driver", "cargo-clippy", "rust-analyzer"}


def _as(user: str, *cmd: str) -> str:
    """Run as the user (their tool managers keep per-user lists)."""
    full = ["runuser", "-u", user, "--", *cmd] if os.geteuid() == 0 and user else list(cmd)
    try:
        return subprocess.run(full, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def tools(user: str, home: Path) -> list[dict]:
    found = []
    try:
        for name in json.loads(_as(user, "mise", "ls", "--installed", "--json") or "{}"):
            found.append(("mise", name, f"mise use -g {name}"))
    except ValueError:
        pass
    for line in _as(user, "uv", "tool", "list").splitlines():
        if line and not line.startswith(("-", " ")):
            found.append(("uv", line.split()[0], f"uv tool install {line.split()[0]}"))
    try:
        for name in json.loads(_as(user, "npm", "ls", "-g", "--depth=0", "--json") or "{}").get("dependencies", {}):
            if name not in ("npm", "corepack"):
                found.append(("npm", name, f"npm install -g {name}"))
    except ValueError:
        pass
    for line in _as(user, "pipx", "list", "--short").splitlines():
        if line.strip():
            found.append(("pipx", line.split()[0], f"pipx install {line.split()[0]}"))
    cargo = home / ".cargo/bin"
    for f in sorted(cargo.iterdir()) if cargo.is_dir() else []:
        if f.name not in CARGO_OWN:
            found.append(("cargo", f.name, f"cargo install {f.name}"))
    out = [item(f"tool:{mgr}:{name}", "apps", name, "tool", [name], [], "keep", 12,       # D46: you chose it
                f"A command-line tool installed with {mgr}.", "you installed it",
                f"quick to install again ({hint})",
                manager=mgr, reinstall=hint)
           for mgr, name, hint in found]

    own = []
    local_bin = home / ".local/bin"
    for f in sorted(local_bin.iterdir()) if local_bin.is_dir() else []:
        target = os.path.realpath(f)
        if target.startswith(("/usr/", "/opt/", str(home / ".local/share"))):
            continue        # links to what packages and tool managers put elsewhere
        own.append(f)
    if own:
        names = ", ".join(f.name for f in own[:12]) + (" …" if len(own) > 12 else "")
        out.append(item("setting:local-bin", "settings", "Your scripts", "folder", [f.name for f in own],
                        ["~/.local/bin/" + f.name for f in own], "keep", 32,
                        f"Commands in ~/.local/bin: {names}", "small, and some may be things you wrote",
                        "they aren't anywhere else"))
    return out
