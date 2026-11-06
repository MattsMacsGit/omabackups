import pytest

from omabackups.core import config, paths
from omabackups.core.errors import OmaError


def test_defaults_without_a_file(sandbox):
    values = config.load()
    assert values["automatic.on"] is True
    assert values["automatic.every"] == "hourly"
    assert values["away.limit_mb"] == 500
    assert values["health.minutes"] == 120


def test_save_and_load_round_trip(sandbox):
    values = config.load()
    values["automatic.every"] = "daily"
    values["health.on"] = False
    config.save(values)
    assert config.load() == values


def test_a_partial_file_gets_defaults(sandbox):
    paths.config_dir().mkdir(parents=True)
    paths.settings_file().write_text("[away]\nlimit_mb = 900\n")
    values = config.load()
    assert values["away.limit_mb"] == 900
    assert values["automatic.on"] is True


@pytest.mark.parametrize("body", [
    "[away]\nlimit_mb = \"lots\"\n",       # wrong kind
    "[automatic]\nevery = \"monthly\"\n",  # not a choice
    "[automatic]\non = 1\n",               # 1 is not true/false
    "[nonsense]\nx = 1\n",                 # unknown setting
    "this is not toml",
])
def test_mistakes_are_reported_not_ignored(sandbox, body):
    paths.config_dir().mkdir(parents=True)
    paths.settings_file().write_text(body)
    with pytest.raises(OmaError) as caught:
        config.load()
    assert caught.value.code == "bad-settings"
    assert str(paths.settings_file()) in caught.value.details


def test_parse_value(sandbox):
    assert config.parse_value("automatic.on", "off") is False
    assert config.parse_value("away.limit_mb", "250") == 250
    for name, text in (("away.limit_mb", "-5"), ("health.at", "24"), ("nope", "1")):
        with pytest.raises(OmaError):
            config.parse_value(name, text)
