"""Enforce the evaluation boundary on operating code, including UI."""
import ast
from pathlib import Path


def test_no_gt_leak():
    for folder in ("fusion", "ui", "robot"):
        for path in (Path("p2") / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    text = ast.unparse(node)
                    assert "p2.sim" not in text and "p2.eval" not in text, (path, text)
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert not any(x in node.value for x in ("eval_gt", "gt/", "object_poses", "actor_list")), (path, node.value)
