"""House rules for the repo, checked on every run."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "omabackups"
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "pkg", "src/omabackups.egg-info"}


def _files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            if not path.name.endswith((".pkg.tar.zst", ".pyc")):
                yield path


def test_no_file_over_400_lines():
    long = [str(p.relative_to(ROOT)) for p in _files()
            if p.suffix in (".py", ".qml", ".js", ".sh", ".md", "")
            and len(p.read_bytes().splitlines()) > 400]
    assert not long, f"split these (over ~400 lines): {long}"


def test_no_agent_files_in_the_repo():
    # Plugin store rule.
    names = {p.name for p in _files()} | {p.name for p in ROOT.rglob(".claude")}
    assert not names & {"CLAUDE.md", "AGENTS.md", ".claude"}


def test_only_events_print_to_stdout():
    # Answers go through core/events.py; everything else logs (BUILD 8.2).
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "events.py" or path.relative_to(SRC) == Path("core/log.py"):
            continue  # events writes answers; log only names stdout to steer away from it
        text = path.read_text()
        if re.search(r"\bprint\(|sys\.stdout", text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_standard_library_only():
    allowed_third_party = set()  # D19: add here only with a decision in BUILD §4
    import ast
    imports = set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imports |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imports.add(node.module.split(".")[0])
    import sys
    outside = {m for m in imports
               if m != "omabackups" and m not in sys.stdlib_module_names} - allowed_third_party
    assert not outside, outside


def test_the_package_installs_every_file_the_code_needs():
    """known.json was once left out (the recipe copied only *.py)."""
    recipe = (ROOT / "packaging" / "PKGBUILD").read_text()
    data = [p for p in SRC.rglob("*") if p.is_file() and p.suffix not in (".py", ".pyc")
            and "__pycache__" not in p.parts]
    assert data, "expected data files (e.g. audit/known.json)"
    assert "-name '*.py'" not in recipe, "the recipe would leave out " + ", ".join(p.name for p in data)
    assert "find omabackups -type f" in recipe
