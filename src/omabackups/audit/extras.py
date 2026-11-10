"""The desktop's extras and your own automation (D46), each a row only when
there's something of yours there (what Omarchy or an app put there isn't):
fonts, icons & cursors, default apps, file manager bookmarks, app
launchers, apps started at login, your own services, scheduled jobs,
desktop settings (dconf), Flatpak permission changes.

Found by looking at other migration tools (SaveDesktop, Konsave, Mackup,
Migration Assistant, Windows Backup): what they carry that 2.0 didn't.
"""

from pathlib import Path

from omabackups.audit import omarchy
from omabackups.audit.model import item

UNITS = (".service", ".timer", ".path", ".socket", ".target")
KEEP = "your own, and it isn't anywhere else"

# (id, name, places under home, what it is, without it)
PLACES = (
    ("fonts", "Your fonts", (".local/share/fonts", ".fonts"),
     "Fonts you added (a theme's clock font, say).", "the apps that use them fall back to another font"),
    ("icons", "Icons & cursors", (".local/share/icons", ".icons"),
     "Icon and cursor sets you added.", "the standard icons"),
    ("mime", "Default apps", (".config/mimeapps.list",),
     "Which app opens what: links, PDFs, pictures, videos.", "this Omarchy's choices"),
    ("bookmarks", "File manager bookmarks", (".config/gtk-3.0/bookmarks",),
     "The places in your file manager's sidebar.", "adding them again by hand"),
    ("dconf", "Desktop settings", (".config/dconf/user",),
     "Settings GTK apps keep in one place (the file manager's view, for example).",
     "those apps start with their standard settings"),
    ("flatpak-overrides", "Flatpak permissions", (".local/share/flatpak/overrides",),
     "Changes you made to what Flatpak apps may use.", "the apps' standard permissions"),
)


def _something(p: Path) -> bool:
    return p.is_file() and p.stat().st_size > 0 or p.is_dir() and any(p.iterdir())


def _launchers(home: Path) -> list[Path]:
    folder = home / ".local/share/applications"
    stock = omarchy.default_webapps()
    out = []
    for f in sorted(folder.glob("*.desktop")) if folder.is_dir() else []:
        text = f.read_text(errors="replace")
        if f.name in stock or "omarchy-launch-webapp" in text or "--app=" in text:
            continue          # Omarchy's own, or a web app (its own rows)
        out.append(f)
    return out


def _autostart(home: Path) -> list[Path]:
    made = {p.name for d in (Path("/etc/xdg/autostart"), Path("/usr/share/applications"),
                             omarchy.SHARE / "config/autostart") if d.is_dir() for p in d.iterdir()}
    folder = home / ".config/autostart"
    return [f for f in sorted(folder.glob("*.desktop")) if f.name not in made] if folder.is_dir() else []


def _services(home: Path) -> list[Path]:
    folder = home / ".config/systemd/user"
    if not folder.is_dir():
        return []
    units = [f for f in sorted(folder.iterdir()) if f.suffix in UNITS and f.is_file() and not f.is_symlink()]
    names = {u.name for u in units}
    wants = [w for d in folder.glob("*.wants") for w in d.iterdir() if w.name in names]
    return units + wants


def extras(home: Path, user: str, finder) -> list[dict]:
    out = []
    t = finder.tilde

    def add(id_, name, paths, what, back, group="desktop", weight=45):
        paths = [p for p in paths if p not in finder.claimed]
        if paths:
            finder.claim(paths)
            out.append(item(f"extra:{id_}", group, name, "folder", [id_], [t(p) for p in paths], "keep",
                            weight, what, KEEP, back))

    for id_, name, places, what, back in PLACES:
        add(id_, name, [home / p for p in places if _something(home / p)], what, back)
    add("launchers", "Your app launchers", _launchers(home),
        "Launchers you made or changed in the app menu.", "making them again")
    add("autostart", "Apps you start at login", _autostart(home),
        "Apps you set to open by themselves when you log in.", "starting them by hand")
    add("user-services", "Your own services", _services(home),
        "Background jobs and timers you set up for your user (systemctl --user).",
        "setting them up again", group="terminal")
    cron = Path(f"/var/spool/cron/{user}")
    if user and cron.is_file() and cron.stat().st_size > 0:
        out.append(item("extra:crontab", "terminal", "Scheduled jobs", "file", ["crontab"], [str(cron)],
                        "keep", 45, "Your crontab: commands that run on a schedule.", KEEP,
                        "setting them up again", needs_admin=True))
    return out
