"""Every name the code uses is defined somewhere (a cheap stand-in for a linter:
a deleted helper once crashed setup at its last step, where no test reached)."""

import ast
import builtins
from pathlib import Path

ROOTS = [Path(__file__).parent.parent / "src", Path(__file__).parent.parent / "server"]


def bound(tree: ast.AST) -> set[str]:
    names = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            names.add(node.name)
    return names


def test_no_name_is_used_that_nothing_defines():
    missing = []
    for root in ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(), str(path))
            known = bound(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in known:
                    missing.append(f"{path.relative_to(root.parent)}:{node.lineno} {node.id}")
    assert not missing, "\n".join(missing)
