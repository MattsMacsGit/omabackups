"""OmaBackups' own disks and the Rescue USB are listed, never opened on their
own (audit 7.4; 1.x share/99-oma-backups.rules, lib/udiskie-rule.sh)."""

from pathlib import Path

from omabackups.setup import udiskie

RULES = Path(__file__).resolve().parent.parent / "packaging/files/99-omabackups.rules"


def test_the_rule_names_every_part():
    text = RULES.read_text()
    for label in ("OmaBackups", "omabackups", "OMABACKUPS_RESCUE", "ARCHISO_EFI", "OMABACKUPS"):
        assert f'=="{label}"' in text, label
    assert 'ENV{ID_PART_ENTRY_NAME}=="OmaBackups", ENV{UDISKS_AUTO}="0"' in text     # listed
    assert 'ENV{ID_FS_LABEL}=="OMABACKUPS", ENV{ID_FS_TYPE}=="vfat", ENV{UDISKS_IGNORE}="1"' in text   # the key


def test_udiskie_gets_its_block_once_and_loses_it_cleanly(sandbox):
    conf = sandbox.home / ".config/udiskie/config.yml"
    assert udiskie.install() == ""
    assert udiskie.install() == ""                     # once
    assert conf.read_text().count(udiskie.BEGIN) == 1
    udiskie.remove()
    assert not conf.exists() and not conf.parent.exists()


def test_your_own_udiskie_settings_are_kept(sandbox):
    conf = sandbox.home / ".config/udiskie/config.yml"
    conf.parent.mkdir(parents=True)
    conf.write_text("program_options:\n  tray: true\n")
    udiskie.install()
    assert conf.read_text().startswith("program_options:\n  tray: true\n") and udiskie.BEGIN in conf.read_text()
    udiskie.remove()
    assert conf.read_text() == "program_options:\n  tray: true\n"


def test_a_device_config_of_your_own_is_never_touched(sandbox):
    conf = sandbox.home / ".config/udiskie/config.yml"
    conf.parent.mkdir(parents=True)
    conf.write_text("device_config:\n  - id_uuid: abc\n    ignore: true\n")
    note = udiskie.install()
    assert "left alone" in note and "should_automount: false" in note
    assert udiskie.BEGIN not in conf.read_text()
