"""The few things `omabackups setup server` does as root on the server, once
(with the server login's sudo password, typed by the user). Never reachable
through SSH keys: the relay only ever calls `serve` verbs.

  admin init STORE                    set the backup store folder
  admin add-computer SYSTEM LABEL     a computer's key (public key on stdin)
  admin remove-key KEY
  admin keys                          list the keys (JSON)
"""

import json
import os
import sys
from pathlib import Path

import conf
import registry
from registry import Refused


def init(store: str) -> dict:
    folder = Path(store)
    if not folder.is_absolute():
        raise Refused("the store must be a full path")
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    conf.SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    registry._write_atomic(conf.SETTINGS, json.dumps({"store": str(folder)}) + "\n", 0o644)
    with registry.changing():
        pass  # makes the registry and authorized_keys if they aren't there
    return {"store": str(folder)}


def current_store() -> str:
    try:
        return json.loads(conf.SETTINGS.read_text())["store"]
    except (OSError, ValueError, KeyError):
        return ""


def main(argv: list[str]) -> int:
    if not conf.TEST and os.geteuid() != 0:
        sys.stderr.write("omabackups-gate admin: run as root\n")
        return 1
    try:
        if argv[:1] == ["init"] and len(argv) == 2:
            result = init(argv[1])
        elif argv[:1] == ["add-computer"] and len(argv) == 3:
            with registry.changing() as data:
                kid = registry.add_key(data, sys.stdin.read(conf.MAX_SECRET), "computer",
                                       argv[2], system=argv[1])
            result = {"key": kid}
        elif argv[:1] == ["remove-key"] and len(argv) == 2:
            with registry.changing() as data:
                registry.remove_key(data, argv[1])
            result = {"removed": argv[1]}
        elif argv[:1] == ["keys"] and len(argv) == 1:
            data = registry.load()
            result = {kid: {k: v for k, v in key.items() if k != "pub"}
                      for kid, key in data["keys"].items()}
        else:
            sys.stderr.write(__doc__)
            return 2
    except Refused as exc:
        sys.stderr.write(f"omabackups-gate: {exc}\n")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
