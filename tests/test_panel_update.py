"""D62: the panel offers Update it when the omabackups package is older than
the panel (a plugin update brings the panel, not the package)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "plugin"


def older(a, b):
    """Model.js's older(), run by node (as the panel runs it)."""
    if not shutil.which("node"):
        pytest.skip("node isn't installed")
    code = (PLUGIN / "Model.js").read_text().replace(".pragma library", "")
    done = subprocess.run(["node", "-e", code + f"\nprocess.stdout.write(JSON.stringify(older({json.dumps(a)}, "
                                            f"{json.dumps(b)})))"], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.parametrize("package, panel, says", [
    ("2.0.3", "2.0.4", True), ("2.0.4", "2.0.4", False), ("2.0.5", "2.0.4", False),
    ("1.9.9", "2.0.0", True), ("2.0.10", "2.0.9", False), ("2.0.4", "2.0.5.dev1", True),
    ("", "2.0.4", False), ("2.0.4", "", False), ("odd", "2.0.4", False)])
def test_only_an_older_package_is_called_older(package, panel, says):
    assert older(package, panel) is says


def test_status_tells_the_panel_the_packages_version():
    from omabackups import __version__
    from omabackups.commands import status_data
    assert '"version": __version__' in Path(status_data.__file__).read_text()
    assert __version__ == json.loads((PLUGIN.parent / "manifest.json").read_text())["version"]


def test_the_update_line_runs_the_install_build():
    service = (PLUGIN / "Service.qml").read_text()
    assert 'action: "update"' in service and "Model.older(packageVersion, panelVersion)" in service
    for page in ("pages/Everyday.qml", "pages/Start.qml"):
        assert 'modelData.action === "update") page.service.installPackage()' in (PLUGIN / page).read_text()
