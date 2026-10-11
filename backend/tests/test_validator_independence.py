"""SPEC §20.2 — the validator imports only .models and the standard library."""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "railflow" / "validator.py"
STDLIB_OK = {"collections", "dataclasses", "typing", "itertools", "__future__"}


def test_validator_imports_only_models_and_stdlib():
    for node in ast.walk(ast.parse(SRC.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                assert node.module == "models", f"validator imports .{node.module}"
            else:
                assert (node.module or "").split(".")[0] in STDLIB_OK, f"validator imports {node.module}"
        if isinstance(node, ast.Import):
            for n in node.names:
                assert n.name.split(".")[0] in STDLIB_OK, f"validator imports {n.name}"
