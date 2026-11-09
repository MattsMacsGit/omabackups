"""Apps that must be closed before their settings come back (1.x, D41).

These apps rewrite their settings when they quit: left open while Migrate
puts the old settings in, they'd write the new install's over them on the
way out. Migrate asks for them to be closed first, and waits.
"""

import subprocess

# A settings folder -> the app (its process name) that holds it open.
CLOSE_FIRST = {
    "~/.config/chromium": ("Chromium", "chromium"),
    "~/.config/google-chrome": ("Google Chrome", "chrome"),
    "~/.config/BraveSoftware": ("Brave", "brave"),
    "~/.mozilla/firefox": ("Firefox", "firefox"),
    "~/.thunderbird": ("Thunderbird", "thunderbird"),
    "~/.config/Code": ("VS Code", "code"),
    "~/.config/Signal": ("Signal", "signal-desktop"),
}


def holders(home_items: list[str]) -> list[tuple[str, str]]:
    """The apps whose settings are among the ones coming back."""
    out = []
    for path in home_items:
        path = path if path.startswith("~/") else "~/" + path.lstrip("/")
        for folder, app in CLOSE_FIRST.items():
            if (path == folder or path.startswith(folder + "/") or folder.startswith(path + "/")) \
                    and app not in out:
                out.append(app)
    return out


def still_open(apps: list[tuple[str, str]], user: str) -> list[str]:
    """Which of them are running for this user now (their names)."""
    return [name for name, process in apps
            if subprocess.run(["pgrep", "-u", user, "-x", process], capture_output=True).returncode == 0]
