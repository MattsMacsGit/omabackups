"""Every program the Rescue USB runs is on its list (rescue/iso/programs.txt),
which build.sh checks against the built image. partprobe was once called but
never put on the stick, and the first real rescue stopped at the disk step."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omabackups"
LIST = ROOT / "rescue" / "iso" / "programs.txt"
NAME = re.compile(r"^[a-z][a-z0-9.+_-]*$")
# Words that start a list but aren't programs: gum's and iwctl's own words, labels.
NOT_PROGRAMS = {"choose", "confirm", "input", "spin", "style", "station", "kept", "newest"}


def _stick_code():
    yield from (SRC / "rescue").glob("*.py")
    yield from (SRC / "restore" / f for f in ("newdisk.py", "bootfix.py", "system.py"))
    yield from (SRC / "where").glob("*.py")


def _called() -> dict[str, str]:
    """Program names: the first word of a command list, or of newdisk's _run()."""
    found = {}
    for path in _stick_code():
        for node in ast.walk(ast.parse(path.read_text())):
            first = None
            if isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant):
                first = node.elts[0].value
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_run" and node.args \
                    and isinstance(node.args[0], ast.Constant):
                first = node.args[0].value
            if isinstance(first, str) and NAME.match(first) and first not in NOT_PROGRAMS:
                found.setdefault(first, f"{path.name}:{node.lineno}")
    return found


def _listed() -> set[str]:
    return {line.strip() for line in LIST.read_text().splitlines() if line.strip() and not line.startswith("#")}


def test_every_program_the_rescue_runs_is_on_the_sticks_list():
    missing = {name: where for name, where in _called().items() if name not in _listed()}
    assert not missing, f"add to rescue/iso/programs.txt (and its package to packages.x86_64): {missing}"


def test_partprobe_is_not_relied_on():
    assert "partprobe" not in _called()


def test_build_checks_the_list_against_the_image():
    build = (ROOT / "rescue" / "iso" / "build.sh").read_text()
    assert "programs.txt" in build
