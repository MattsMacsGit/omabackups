"""Logging: to the log file, and to stderr when asked. NEVER to stdout.

stdout is reserved for answers and JSON events. In 1.x a log line printed to
stdout inside a captured function became a user name (BUILD 8.2).
"""

import logging
import sys

from omabackups.core import paths

NAME = "omabackups"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _NeverStdout(logging.StreamHandler):
    """A stderr handler that refuses to be pointed at stdout."""

    def __init__(self):
        super().__init__(sys.stderr)

    def emit(self, record):
        if self.stream is sys.stdout or self.stream is sys.__stdout__:
            self.stream = sys.stderr
        super().emit(record)


def get(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{NAME}.{name}" if name else NAME)


def setup(verbose: bool = False) -> logging.Logger:
    """Set up logging once per run. Safe to call again (it resets)."""
    logger = logging.getLogger(NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    try:
        paths.log_dir().mkdir(parents=True, exist_ok=True)
        to_file = logging.FileHandler(paths.log_file(), encoding="utf-8")
        to_file.setLevel(logging.DEBUG)
        to_file.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(to_file)
    except OSError:
        pass  # a missing log file must never stop a backup; stderr still works

    to_stderr = _NeverStdout()
    to_stderr.setLevel(logging.DEBUG if verbose else logging.WARNING)
    to_stderr.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(to_stderr)
    return logger
