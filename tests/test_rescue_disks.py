"""The rescue never offers the stick it's running from, even when the rescue
system was copied into memory and the stick unmounted (it was offered)."""

from omabackups.rescue import disks


def _tree(disk: str, part: str) -> dict:
    return {"blockdevices": [{"path": part, "type": "part", "children": [{"path": disk, "type": "disk"}]}]}


def test_the_stick_is_found_by_its_id_on_the_boot_line(monkeypatch, tmp_path):
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("BOOT_IMAGE=/arch/boot/x86_64/vmlinuz archisobasedir=arch "
                       "archisosearchuuid=2026-11-11-03-28-15-00 copytoram\n")
    monkeypatch.setattr(disks, "CMDLINE", cmdline)
    monkeypatch.setattr(disks, "_source", lambda where: "")          # copied to RAM: nothing mounted
    monkeypatch.setattr(disks, "_with_id", lambda uuid: ["/dev/sdz1"] if uuid == "2026-11-11-03-28-15-00" else [])
    monkeypatch.setattr(disks.setup_disks, "_lsblk", lambda *a: _tree("/dev/sdz", "/dev/sdz1"))
    assert disks.stick() == {"/dev/sdz"}


def test_the_mounted_stick_or_its_settings_part_count_too(monkeypatch, tmp_path):
    monkeypatch.setattr(disks, "CMDLINE", tmp_path / "missing")
    monkeypatch.setattr(disks, "_source", lambda where: "/dev/sdy3" if "omabackups-rescue" in where else "")
    monkeypatch.setattr(disks.setup_disks, "_lsblk", lambda *a: _tree("/dev/sdy", a[-1]))
    assert disks.stick() == {"/dev/sdy"}


def _labels(monkeypatch, names, mine):
    from omabackups.rescue import screens, wizard
    shown = {}

    class Gate:
        def call(self, verb, *args):
            return {"points": names, "kept": {}}
    monkeypatch.setattr(screens, "step", lambda *a: None)
    monkeypatch.setattr(screens, "choose", lambda header, options, selected=0: shown.update(o=options) or 0)
    monkeypatch.setattr(wizard, "_when", lambda name: name[4:])
    wizard.pick_point(Gate(), "b", "h", mine)
    return shown["o"]


def test_restore_points_read_as_the_computer_and_its_line(monkeypatch):
    """They all said "an earlier computer (line 001)": a first line isn't
    written down, so the line was unknown."""
    shown = _labels(monkeypatch, ["001-2026-11-12-1954", "001-2026-11-12-1955"],
                    {"computer": "omarchy", "line": None})
    assert shown == ["omarchy-001  ·  2026-11-12-1955  (newest)", "omarchy-001  ·  2026-11-12-1954"]


def test_an_older_line_from_before_a_migrate_says_earlier(monkeypatch):
    shown = _labels(monkeypatch, ["002-2026-11-12-1955", "001-2026-11-01-0900"],
                    {"computer": "omarchy", "line": "002"})
    assert shown == ["omarchy-002  ·  2026-11-12-1955  (newest)", "earlier-001  ·  2026-11-01-0900"]
