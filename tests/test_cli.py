"""The real command, run as a separate process in the sandbox."""

import json

from omabackups import CONTRACT


def _json_lines(stdout: str) -> list[dict]:
    # Every single line on stdout must be JSON: a stray log line fails here.
    return [json.loads(line) for line in stdout.splitlines()]


def test_status_says_not_set_up(sandbox):
    done = sandbox.run("status")
    assert done.returncode == 0, done.stderr
    assert "not set up" in done.stdout
    assert done.stderr == ""


def test_status_json_is_one_result(sandbox):
    done = sandbox.run("--json", "status")
    assert done.returncode == 0, done.stderr
    events = _json_lines(done.stdout)
    assert len(events) == 1
    result = events[0]
    assert result["event"] == "result" and result["contract"] == CONTRACT
    assert result["flow"] == "not-set-up"
    assert len(result["system"]["id"]) == 32


def test_verbose_logs_go_to_stderr_never_stdout(sandbox):
    done = sandbox.run("--json", "--verbose", "status")
    assert done.returncode == 0
    _json_lines(done.stdout)
    assert "omabackups" in done.stderr  # the debug line went to stderr


def test_the_log_file_is_written(sandbox):
    sandbox.run("status")
    log = sandbox.home / ".local/state/omabackups/logs/omabackups.log"
    assert "status" in log.read_text()


def test_settings_set_then_get(sandbox):
    assert sandbox.run("settings", "set", "away.limit_mb", "800").returncode == 0
    done = sandbox.run("--json", "settings", "get", "away.limit_mb")
    assert _json_lines(done.stdout)[0]["settings"] == {"away.limit_mb": 800}


def test_user_errors_are_plain_and_json(sandbox):
    done = sandbox.run("--json", "settings", "set", "away.limit_mb", "lots")
    assert done.returncode == 1
    error = _json_lines(done.stdout)[0]
    assert error["event"] == "error" and error["code"] == "bad-setting"
    assert error["what"] and error["todo"]
    assert "can't be used" in done.stderr
    assert "Traceback" not in done.stderr


def test_bugs_still_get_a_proper_message(sandbox):
    (sandbox.sysroot / "etc" / "machine-id").unlink()
    done = sandbox.run("status")
    assert done.returncode == 1
    assert "can't tell which computer this is" in done.stderr
    assert done.stdout == ""


def test_version(sandbox):
    done = sandbox.run("--version")
    assert done.returncode == 0 and done.stdout.startswith("omabackups 2.0")


def test_stop_stops_every_kind_of_backup(monkeypatch):
    """Stop once missed the away question's "anyway" backup."""
    from omabackups.commands import backup
    stopped = []
    monkeypatch.setattr(backup, "_systemctl", lambda *a: stopped.append(a) or None)

    class Quiet:
        def result(self, *a):
            pass
    backup.run_stop(None, Quiet())
    assert {a[1] for a in stopped if a[0] == "stop"} == {backup.UNIT.format(k) for k in backup.KINDS}
    assert "anyway" in backup.KINDS


def test_a_stopped_backup_isnt_shown_as_running(sandbox):
    """Killed or stopped, the progress file still says running: the service decides."""
    from omabackups.backup import progress
    from test_migrate_apply import fake_state
    fake_state(sandbox, active=["omabackups-backup@anyway.service"])
    data = {"running": True, "kind": "anyway", "step": "send"}
    assert progress.alive(data)
    fake_state(sandbox, active=[])
    assert not progress.alive(data)
    assert not progress.alive({"running": False, "kind": "now"})
