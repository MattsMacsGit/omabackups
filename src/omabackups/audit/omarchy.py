"""THE Omarchy part of the audit (D2): everything that knows what Omarchy is.

Its version, the packages a fresh Omarchy installs, the files it makes, and
each piece of the desktop setup (keybindings, screens, bar, theme,
backgrounds, menus, hooks, plugins) compared with Omarchy's own copy: a piece
is "yours" when it differs from what a fresh install would have.
Another system (D21) would get its own module like this one.
"""

import filecmp
import os
import platform
import re
import subprocess
from pathlib import Path

from omabackups.audit.model import item

SHARE = Path("/usr/share/omarchy")
INSTALLER = re.compile(r"^(base|base-devel|sudo|mkinitcpio|grub|efibootmgr|systemd-boot|limine.*|"
                       r".+-ucode|linux(-lts|-zen|-hardened|-omarchy|-t2)?(-headers)?|linux-firmware.*)$")

HYPR = {
    "bindings.lua": ("Keybindings", "Your keyboard shortcuts.", 92),
    "monitors.lua": ("Screen setup", "Your screens: resolution, scaling, position.", 75),
    "input.lua": ("Keyboard, mouse & touchpad", "Layout, repeat speed, scrolling, touchpad.", 80),
    "looknfeel.lua": ("Look and feel", "Gaps, borders, rounding and animations.", 78),
    "autostart.lua": ("Apps started at login", "What opens by itself when you log in.", 76),
    "hyprland.lua": ("Hyprland main settings", "The window manager's main settings file.", 70),
    "hyprsunset.conf": ("Night light", "When the screen warms up at night.", 60),
}
KEEP_DESKTOP = "it's part of what makes this desktop yours"
BACK_DESKTOP = "a fresh Omarchy has the standard one instead"


def _out(cmd: list[str]) -> subprocess.CompletedProcess:
    """A command's result; a missing program is simply nothing found."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(cmd, 127, "", "")


def version() -> str:
    out = _out(["omarchy-version"]).stdout.strip()
    if out:
        return out
    try:
        return (SHARE / "version").read_text().strip()
    except OSError:
        return ""


def stock_packages() -> set[str]:
    """What a fresh Omarchy installs (its install lists for this machine,
    and everything the omarchy package pulls in)."""
    arch, names = platform.machine(), {"omarchy"}
    for f in (SHARE / "install").glob("*.packages"):
        if ("aarch64" in f.name and arch != "aarch64") or ("x86_64" in f.name and arch != "x86_64"):
            continue
        for line in f.read_text(errors="replace").splitlines():
            names.update(line.split("#", 1)[0].split())
    names.update(_out(["pactree", "-lu", "omarchy"]).stdout.split())
    return names


def installer_package(name: str) -> bool:
    return bool(INSTALLER.match(name))


def default_webapps() -> set[str]:
    return {f.name for f in (SHARE / "applications").glob("*.desktop")}


def made_by_omarchy(path: Path) -> bool:
    """A file in /etc that Omarchy itself puts there."""
    stock = SHARE / "etc-overrides" / path.relative_to("/")
    if stock.exists() or path.name.startswith("omarchy"):
        return True
    key = "/".join(path.parts[-3:] if path.parent.name in ("bin", "sbin") else path.parts[-2:])
    return _out(["grep", "-rlqF", key, str(SHARE / "install"), str(SHARE / "migrations"),
                 str(SHARE / "default")]).returncode == 0


def _differs(stock: Path, mine: Path) -> list[str]:
    """Files under `mine` that differ from `stock` or that stock doesn't have."""
    if not mine.exists():
        return []
    if mine.is_file():
        return [] if stock.is_file() and filecmp.cmp(stock, mine, shallow=False) else [str(mine)]
    out = []
    for root, dirs, files in os.walk(mine):
        dirs[:] = [d for d in dirs if d not in ("cache", "Cache", ".git")]
        for name in files:
            m = Path(root) / name
            s = stock / m.relative_to(mine)
            if not (s.is_file() and filecmp.cmp(s, m, shallow=False)):
                out.append(str(m))
    return out


def _tilde(path, home: Path) -> str:
    text = str(path)
    return "~" + text[len(str(home)):] if text.startswith(str(home)) else text


def desktop(home: Path, claimed: set = frozenset()) -> list[dict]:
    """Keybindings, bar & theme; Backgrounds; and Omarchy's app settings."""
    out, cfg, stock = [], home / ".config", SHARE / "config"
    t = lambda p: _tilde(p, home)  # noqa: E731

    for name, (title, what, weight) in HYPR.items():
        if _differs(stock / "hypr" / name, cfg / "hypr" / name):
            out.append(item(f"desktop:hypr/{name}", "desktop", title, "config", [f"hypr/{name}"],
                            [t(cfg / "hypr" / name)], "keep", weight, what, KEEP_DESKTOP, BACK_DESKTOP))
    for extra in sorted((cfg / "hypr").glob("*")) if (cfg / "hypr").is_dir() else []:
        if extra.name not in HYPR and not (stock / "hypr" / extra.name).exists():
            out.append(item(f"desktop:hypr/{extra.name}", "desktop", f"Hyprland: {extra.name}", "config",
                            [f"hypr/{extra.name}"], [t(extra)], "keep", 60,
                            "A Hyprland file you added.", KEEP_DESKTOP, BACK_DESKTOP))

    om = cfg / "omarchy"
    if _differs(stock / "omarchy" / "shell.json", om / "shell.json"):
        out.append(item("desktop:shell", "desktop", "The bar and shell", "config", ["omarchy/shell.json"],
                        [t(om / "shell.json")], "keep", 88,
                        "Your bar: its layout and widgets, and when the screen locks.",
                        KEEP_DESKTOP, BACK_DESKTOP))
    for kind, title, weight in (("extensions", "Menu", 55), ("themed", "Theme template", 50)):
        for f in _differs(stock / "omarchy" / kind, om / kind):
            if not f.endswith(".sample"):
                out.append(item(f"desktop:{kind}/{Path(f).name}", "desktop", f"{title}: {Path(f).name}",
                                "config", [f"omarchy/{kind}/{Path(f).name}"], [t(f)], "keep", weight,
                                f"Your {title.lower()} for Omarchy.", KEEP_DESKTOP, BACK_DESKTOP))
    for f in _differs(stock / "omarchy" / "hooks", om / "hooks"):
        if not f.endswith(".sample"):
            hook = Path(f).parent.name.removesuffix(".d")
            out.append(item(f"desktop:hook/{hook}/{Path(f).name}", "desktop",
                            f"Automation: {Path(f).name} ({hook})", "config", [f"hooks/{hook}"], [t(f)],
                            "keep", 58, f"A script Omarchy runs for you on {hook.replace('-', ' ')}.",
                            "you set this up yourself", "a fresh Omarchy doesn't have it"))
    for p in sorted((om / "plugins").iterdir()) if (om / "plugins").is_dir() else []:
        linked = p.is_symlink() and not os.path.realpath(p).startswith(str(home))
        out.append(item(f"desktop:plugin/{p.name}", "desktop", f"Bar plugin: {p.name}", "config",
                        [p.name], [t(p)], "you" if linked else "keep", 52,
                        "A plugin on your bar" + (" (it comes with an app you installed)" if linked else "."),
                        "it comes back with its app" if linked else "you added it",
                        "reinstalling the app brings it back" if linked else "a fresh Omarchy doesn't have it"))
    for p in sorted((om / "themes").iterdir()) if (om / "themes").is_dir() else []:
        out.append(item(f"desktop:theme/{p.name}", "desktop", f"Your theme: {p.name}", "folder", [p.name],
                        [t(p)], "keep", 70, "A theme you made or changed.", KEEP_DESKTOP,
                        "it isn't anywhere else"))
    current = home / ".local/state/omarchy/current/theme.name"
    if current.exists():
        name = current.read_text().strip()
        out.append(item("desktop:theme-current", "desktop", f"Theme in use: {name}", "config", [name],
                        [t(current)], "keep", 86, "The theme your desktop uses now.", KEEP_DESKTOP,
                        "a fresh Omarchy starts with its standard theme"))
    for p in sorted((om / "backgrounds").iterdir()) if (om / "backgrounds").is_dir() else []:
        out.append(item(f"backgrounds:{p.name}", "backgrounds", f"Backgrounds for {p.name}", "folder",
                        [p.name], [t(p)], "keep", 65, "Pictures you added for this theme.",
                        "your own pictures", "they aren't anywhere else"))
    # (Branding has no stock copy to compare with: Omarchy makes it at install.)

    for entry in sorted(stock.iterdir()) if stock.is_dir() else []:
        mine = cfg / entry.name
        if entry.name in ("hypr", "omarchy") or any(c == mine or mine in c.parents or c in mine.parents
                                                    for c in claimed):
            continue      # listed already (e.g. "Chromium profile" is ~/.config/chromium)
        if _differs(entry, mine):
            out.append(item(f"settings:omarchy-config/{entry.name}", "settings",
                            f"Settings: {entry.name}", "config", [entry.name], [t(mine)], "you", 25,
                            f"Changed since Omarchy set up {entry.name}: by you, or by the app itself "
                            "saving its own state.",
                            "bring it over if you changed it yourself",
                            "a fresh Omarchy has the standard settings"))
    return out


def webapps(home: Path) -> list[dict]:
    folder, out, stock = home / ".local/share/applications", [], default_webapps()
    for f in sorted(folder.glob("*.desktop")) if folder.is_dir() else []:
        if f.name in stock:
            continue
        text = f.read_text(errors="replace")
        exec_line = next((x[5:] for x in text.splitlines() if x.startswith("Exec=")), "")
        if "omarchy-launch-webapp" not in exec_line and "--app=" not in exec_line:
            continue
        name = next((x[5:] for x in text.splitlines() if x.startswith("Name=")), f.stem)
        out.append(item(f"webapp:{f.stem}", "apps", f"{name} (web app)", "webapp", [f.name],
                        [_tilde(f, home)], "keep", 30, "A web app you added to the app menu.",
                        "Omarchy's standard web apps come back by themselves; this one doesn't",
                        "quick to add again, if you remember its address"))
    return out
