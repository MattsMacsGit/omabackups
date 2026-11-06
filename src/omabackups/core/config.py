"""Settings: what the user can change in Settings (BUILD 6.1 E).

Stored as TOML in the user's config folder. Anything missing gets its
default; anything wrong is reported plainly, never silently ignored.
Only settings the spec describes live here (D18, D17).
"""

import tomllib
from dataclasses import dataclass

from omabackups.core import paths
from omabackups.core.errors import OmaError
from omabackups.core.state import write_atomic


@dataclass(frozen=True)
class Setting:
    section: str
    key: str
    default: object
    choices: tuple = ()  # allowed values; empty = any value of the default's type
    explain: str = ""


SETTINGS = (
    Setting("automatic", "on", True, explain="Automatic backups"),
    Setting("automatic", "every", "hourly", ("hourly", "daily", "weekly"),
            "How often automatic backups run"),
    Setting("away", "limit_mb", 500, explain="Away from home: size limit (MB) before asking"),
    Setting("health", "on", True, explain="Nightly health check"),
    Setting("health", "at", 0, tuple(range(24)), "Health check start hour (0-23)"),
    Setting("health", "minutes", 120, (30, 60, 120, 240, 480),
            "Health check: how long each night"),
)

_BY_NAME = {f"{s.section}.{s.key}": s for s in SETTINGS}


def names() -> list[str]:
    return list(_BY_NAME)


def _check(name: str, value):
    setting = _BY_NAME[name]
    kind = type(setting.default)
    # bool is a kind of int in Python; keep them apart.
    if type(value) is not kind:
        raise ValueError(f"{name} must be {_kind_word(kind)}, not {value!r}")
    if setting.choices and value not in setting.choices:
        raise ValueError(f"{name} must be one of {', '.join(map(str, setting.choices))}")
    if kind is int and value < 0:
        raise ValueError(f"{name} can't be below 0")
    return value


def _kind_word(kind) -> str:
    return {bool: "true or false", int: "a whole number", str: "text"}[kind]


def defaults() -> dict:
    return {name: s.default for name, s in _BY_NAME.items()}


def load() -> dict:
    """All settings as {"section.key": value}, defaults filled in."""
    path = paths.settings_file()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaults()
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise _bad(path, str(exc)) from exc

    values = defaults()
    for section, table in raw.items():
        if not isinstance(table, dict):
            raise _bad(path, f"'{section}' should be a [section]")
        for key, value in table.items():
            name = f"{section}.{key}"
            if name not in _BY_NAME:
                raise _bad(path, f"unknown setting '{name}'")
            try:
                values[name] = _check(name, value)
            except ValueError as exc:
                raise _bad(path, str(exc)) from exc
    return values


def parse_value(name: str, text: str):
    """Turn what the user typed into the right kind of value for `name`."""
    if name not in _BY_NAME:
        raise OmaError(f"There is no setting called '{name}'.",
                       f"The settings are: {', '.join(names())}.", code="bad-setting")
    kind = type(_BY_NAME[name].default)
    try:
        if kind is bool:
            if text.lower() not in ("true", "false", "on", "off"):
                raise ValueError(f"{name} must be true or false")
            value = text.lower() in ("true", "on")
        elif kind is int:
            value = int(text)
        else:
            value = text
        return _check(name, value)
    except ValueError as exc:
        raise OmaError(f"'{text}' can't be used for {name}.", str(exc).capitalize() + ".",
                       code="bad-setting") from exc


def save(values: dict) -> None:
    """Write every setting (checked first), atomically."""
    for name, value in values.items():
        if name not in _BY_NAME:
            raise ValueError(f"unknown setting {name}")
        _check(name, value)
    lines = ["# OmaBackups settings. Change them in the panel's Settings,",
             "# or with: omabackups settings set <name> <value>"]
    for section in dict.fromkeys(s.section for s in SETTINGS):
        lines += ["", f"[{section}]"]
        for s in SETTINGS:
            if s.section == section:
                lines.append(f"{s.key} = {_toml(values.get(f'{section}.{s.key}', s.default))}")
    write_atomic(paths.settings_file(), ("\n".join(lines) + "\n").encode("utf-8"), 0o644)


def _toml(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bad(path, why: str) -> OmaError:
    return OmaError(
        "OmaBackups' settings file has a mistake in it.",
        "Fix it in the file, or delete the file to go back to the defaults.",
        f"{path}: {why}",
        code="bad-settings",
    )
