"""Tests for the Modal BigQuery sync entrypoint configuration."""

from __future__ import annotations

import ast
from pathlib import Path

MODAL_ENTRYPOINT_PATH = Path("src/aej_dlt/modal_sync_bigquery.py")


def test_modal_entrypoint_uses_aej_dlt_bigquery_secret() -> None:
    tree = ast.parse(MODAL_ENTRYPOINT_PATH.read_text(encoding="utf-8"))

    secret_name = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SECRET_NAME":
                    secret_name = ast.literal_eval(node.value)

    assert secret_name == "aej-dlt-bq-sync"


def test_modal_entrypoint_exposes_one_deployed_function_and_local_cli() -> None:
    tree = ast.parse(MODAL_ENTRYPOINT_PATH.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

    deployed_functions = [
        node.name for node in functions.values() if _has_app_decorator(node, "function")
    ]
    local_entrypoints = [
        node.name for node in functions.values() if _has_app_decorator(node, "local_entrypoint")
    ]

    assert deployed_functions == ["scheduled_sync"]
    assert local_entrypoints == ["main"]
    assert _boolean_default(functions["scheduled_sync"], "full_refresh") is False
    assert _boolean_default(functions["main"], "full_refresh") is False


def _has_app_decorator(node: ast.FunctionDef, decorator_name: str) -> bool:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue
        if decorator.func.attr == decorator_name:
            return True
    return False


def _boolean_default(node: ast.FunctionDef, argument_name: str) -> bool | None:
    positional_args = node.args.args
    defaults = node.args.defaults
    default_by_name = {
        argument.arg: default
        for argument, default in zip(
            positional_args[-len(defaults) :],
            defaults,
            strict=True,
        )
    }
    default = default_by_name.get(argument_name)
    if isinstance(default, ast.Constant) and isinstance(default.value, bool):
        return default.value
    return None
