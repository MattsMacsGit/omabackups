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


def test_this_computers_newest_comes_first_not_the_highest_line(monkeypatch):
    """D61, seen in the VM: line 003 (another computer, 16 Nov) was first and
    "(newest)"; this computer's line 002 had a point from 25 Nov."""
    shown = _labels(monkeypatch, ["003-2026-11-16-1323", "002-2026-11-25-1652", "002-2026-11-24-1524",
                                  "001-2026-11-15-1209"], {"computer": "new-laptop", "line": "002"})
    assert shown[0] == "new-laptop-002  ·  2026-11-25-1652  (newest)"
    assert shown[1] == "new-laptop-002  ·  2026-11-24-1524"
    assert [s.split("  ·  ")[1] for s in shown[2:]] == ["2026-11-16-1323", "2026-11-15-1209"]
    assert not any("newest" in s for s in shown[1:])


def test_with_none_of_its_own_the_newest_date_comes_first():
    from omabackups.rescue import wizard
    assert wizard.in_order(["003-2026-11-01-0900", "001-2026-11-20-0900"], "002") == \
        ["001-2026-11-20-0900", "003-2026-11-01-0900"]


def test_the_rescue_names_whose_point_it_will_put_back(monkeypatch):
    from omabackups.rescue import screens, wizard

    class Gate:
        def call(self, verb, *args):
            if verb == "points":
                return {"points": ["003-2026-11-16-1323", "002-2026-11-25-1652"], "kept": {}}
            return {"point": {"computer": "omarchy"}}
    monkeypatch.setattr(screens, "step", lambda *a: None)
    monkeypatch.setattr(screens, "choose", lambda header, options, selected=0: 1)   # the other computer's
    monkeypatch.setattr(wizard, "_when", lambda name: name[4:])
    point, _names, whose = wizard.pick_point(Gate(), "b", "h", {"computer": "new-laptop", "line": "002"})
    assert point == "003-2026-11-16-1323" and whose.startswith("omarchy") and "003" in whose
