import pytest

from omabackups.core import flow, ids, state
from omabackups.core.errors import OmaError, unexpected


# --- ids ---------------------------------------------------------------------

def test_system_id_is_stable_and_not_the_machine_id(sandbox):
    from conftest import FAKE_MACHINE_ID
    first = ids.system_id()
    assert first == ids.system_id()
    assert len(first) == 32 and first != FAKE_MACHINE_ID
    assert ids.short(first) == first[:8]


def test_another_machine_gets_another_id(sandbox):
    first = ids.system_id()
    (sandbox.sysroot / "etc" / "machine-id").write_text("f" * 32 + "\n")
    assert ids.system_id() != first


@pytest.mark.parametrize("content", [None, "", "not-an-id\n"])
def test_missing_machine_id_is_explained(sandbox, content):
    path = sandbox.sysroot / "etc" / "machine-id"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    with pytest.raises(OmaError) as caught:
        ids.system_id()
    assert caught.value.code == "no-system-id" and caught.value.todo


# --- flow --------------------------------------------------------------------

def test_new_install_is_not_set_up(sandbox):
    assert flow.where() is flow.Step.NOT_SET_UP


@pytest.mark.parametrize("setup, migrate, expected", [
    ({"where": "server", "first_backup": False}, None, flow.Step.SETTING_UP),
    ({"where": "disk", "first_backup": True}, None, flow.Step.EVERYDAY),
    (None, {"done": False}, flow.Step.MIGRATING),
    (None, {"done": True, "files_restored": False}, flow.Step.RESTORE_FILES),
    (None, {"done": True, "files_restored": True}, flow.Step.SETTING_UP),
    ({"where": "server", "first_backup": True}, {"done": True, "files_restored": True},
     flow.Step.EVERYDAY),
])
def test_flow_steps(sandbox, setup, migrate, expected):
    if setup is not None:
        state.write(flow.SETUP, setup)
    if migrate is not None:
        state.write(flow.MIGRATE, migrate)
    assert flow.where() is expected


# --- errors ------------------------------------------------------------------

def test_error_text_has_all_three_parts():
    text = OmaError("It broke.", "Do this.", "trace here").as_text()
    assert text.splitlines()[:2] == ["It broke.", "Do this."]
    assert "Details to copy:" in text and "trace here" in text


def test_unexpected_errors_carry_the_traceback():
    try:
        raise ZeroDivisionError("oops")
    except ZeroDivisionError as exc:
        error = unexpected(exc)
    assert error.code == "unexpected" and "ZeroDivisionError" in error.details
