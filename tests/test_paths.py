from omabackups.core import paths


def test_everything_lives_under_the_fake_home(sandbox):
    for path in (paths.settings_file(), paths.state_dir(), paths.log_file(), paths.cache_dir()):
        assert sandbox.home in path.parents


def test_names_never_clash_with_1x(sandbox):
    every = [paths.config_dir(), paths.state_dir(), paths.cache_dir(),
             paths.system_config_dir(), paths.system_state_dir(), paths.system_run_dir()]
    for path in every:
        assert path.name == "omabackups"


def test_xdg_variables_are_followed(sandbox, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert paths.settings_file() == tmp_path / "cfg" / "omabackups" / "settings.toml"


def test_relative_xdg_values_are_ignored(sandbox, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "relative/place")
    assert paths.state_dir() == sandbox.home / ".local/state/omabackups"


def test_system_paths_follow_the_sysroot(sandbox):
    assert paths.machine_id_file() == sandbox.sysroot / "etc" / "machine-id"


def test_state_names_cant_escape_the_folder(sandbox):
    import pytest
    for bad in ("", "../x", "a/b", ".hidden"):
        with pytest.raises(ValueError):
            paths.state_file(bad)
