"""The restore itself, on Omarchy's progress screen (stage 9b: 1.x's
restore-to-disk.sh step by step, BUILD-2.0.md's boot checklist).

Stage 9a stops here: everything up to this point is real (the network, your
backup, the password, the restore points, the disks), and nothing has been
changed on any disk.
"""

from omabackups.rescue import screens


def run(events, gate, server, password, point, full, disk, disk_password, mine) -> int:
    screens.step("Everything up to here works",
                 "The restore itself comes in the next build (stage 9b). Nothing was changed on any disk.")
    screens.say(f"You picked: {point}, {'Full' if full else 'Quick'} Rescue, onto {disk.path}.", screens.GREY)
    screens.gap()
    screens.confirm("Back to the start?", "Start again", "Start again")
    events.result({"rescued": False, "stage": "9a"}, "Stage 9a: stopped before the restore.")
    return 1
