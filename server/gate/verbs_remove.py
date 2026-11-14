"""Remove OmaBackups, deleting the backup too (audit 10.2; wording agreed
14 Nov: "Every restore point in it goes, for good. This can't be undone.").

  destroy BACKUP   this computer's backup, every restore point in it, gone
                   (owner only; the computer asked twice first)
"""

import subprocess

import conf
import holds
import registry
from host import host
from registry import Refused
from verbs import Call, _argc, _box


def v_destroy(call: Call) -> dict:
    _argc(call, 1)
    bid = call.args[0]
    backup = registry.the_backup(registry.load(), bid, call.kid, ("owner",))
    h = host()
    with holds.turn(bid):
        if backup.get("device"):                  # a backup disk: its box is a partition
            h.close(bid)
            if not conf.TEST:
                subprocess.run(["wipefs", "-a", backup["device"]], capture_output=True, check=False)
        else:
            h.remove_box(_box(bid), bid)
    for state in (conf.REGISTRY.parent / "health" / f"{bid}.json",):
        state.unlink(missing_ok=True)
    with registry.changing() as data:
        roles = data["backups"].pop(bid, {}).get("roles", {})
        for kid, role in roles.items():
            used = any(kid in b["roles"] for b in data["backups"].values())
            if role == "rescue" and not used:
                data["keys"].pop(kid, None)       # a Rescue USB's key for this backup only
    return {"destroyed": bid}


VERBS = {"destroy": v_destroy}
