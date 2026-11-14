"""The Rescue USB locked with the backup's own password (audit 8.3, decided
14 Nov): one password, checked before the stick is written, asked first on
the stick and never asked again."""

import pytest
from test_run import world  # noqa: F401  (the fixture)

from omabackups.core.errors import OmaError
from omabackups.rescue import settings, wizard
from omabackups.root import job_rescue


def test_the_password_is_checked_before_the_stick_is_touched(world):  # noqa: F811
    with pytest.raises(OmaError) as wrong:
        job_rescue.check_password({"password": "not it"})
    assert wrong.value.code == "wrong-password" and "wasn't touched" in wrong.value.what
    assert job_rescue.check_password({"password": "password1"}) == "password1"
    with pytest.raises(OmaError):
        job_rescue.check_password({})


def test_the_stick_asks_first_and_never_twice(monkeypatch):
    tries, asked = iter([False, True]), []
    monkeypatch.setattr(settings, "unlock", lambda password: next(tries))
    monkeypatch.setattr(wizard.screens, "step", lambda *a: asked.append(a[0]))
    monkeypatch.setattr(wizard.screens, "secret", lambda *a: "pw")
    monkeypatch.setattr(wizard, "_problem", lambda *a, **k: asked.append(a[0]))
    monkeypatch.setattr(wizard.time, "sleep", lambda s: None)
    assert wizard.unlock_stick() == "pw"
    assert asked == ["Unlock the Rescue USB", "That password didn't open this Rescue USB",
                     "Unlock the Rescue USB"]

    class Gate:
        def call(self, verb, bid, data=b""):
            assert data == b"pw"
            return {"hold": "h1"}
    monkeypatch.setattr(wizard.screens, "secret", lambda *a: pytest.fail("asked for the password again"))
    assert wizard.unlock(Gate(), "b", "pw") == ("pw", "h1")


def test_a_failure_is_shown_before_the_window_closes(monkeypatch, capsys):
    """It asked "Press Enter to close" first and printed the error after, so the
    window closed on nothing (demo film, 14 Nov)."""
    from types import SimpleNamespace

    from omabackups.commands import rescue
    from omabackups.core.events import Events
    from omabackups.setup import menu, rescue_usb
    monkeypatch.setattr(__import__("os"), "isatty", lambda fd: True)

    def broken():
        raise OmaError("The stick broke.", "Try another.", code="x")
    monkeypatch.setattr(rescue_usb, "make", broken)
    seen = {}
    monkeypatch.setattr(menu, "ask", lambda prompt, *a, **k: seen.update(on_screen=capsys.readouterr().err) or "")
    assert rescue.run_make(SimpleNamespace(verb="make"), Events()) == 1
    assert "The stick broke." in seen["on_screen"]          # already there when it asks to close


def test_on_the_stick_only_a_real_refusal_is_a_wrong_password(monkeypatch):
    """The demo film's rescue: the backup couldn't be reached (the stick talked
    to itself), and the stick said the password was wrong."""
    said = []
    monkeypatch.setattr(wizard, "_problem", lambda what, *a, **k: said.append(what))
    monkeypatch.setattr(wizard.screens, "step", lambda *a: None)
    monkeypatch.setattr(wizard.screens, "secret", lambda *a: "pw")
    monkeypatch.setattr(wizard.time, "sleep", lambda s: None)
    answers = iter([OmaError("Your backup server can't be reached.", "Check it.", code="unreachable"),
                    OmaError("The backup server said no: that password doesn't open this backup.",
                             code="gate-refused"), {"hold": "h"}])

    class Gate:
        def call(self, verb, bid, data=b""):
            a = next(answers)
            if isinstance(a, OmaError):
                raise a
            return a
    assert wizard.unlock(Gate(), "b", "pw") == ("pw", "h")
    assert said == ["Your backup server can't be reached.", "That password didn't open your backup"]
