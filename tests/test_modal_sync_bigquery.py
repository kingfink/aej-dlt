"""Tests for the Modal BigQuery sync entrypoint configuration."""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
import tomllib
from pathlib import Path

MODAL_ENTRYPOINT_PATH = Path("modal_app.py")
PYPROJECT_PATH = Path("pyproject.toml")


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

    assert deployed_functions == ["sync"]
    assert local_entrypoints == ["main"]
    assert _boolean_default(functions["sync"], "full_refresh") is False
    assert _boolean_default(functions["main"], "full_refresh") is False


def test_clone_repo_uses_git_askpass_for_github_token(monkeypatch, tmp_path) -> None:
    module = _load_modal_entrypoint(monkeypatch)
    calls = []

    def fake_run(args, *, check, env=None):
        calls.append({"args": args, "check": check, "env": env})
        askpass_path = Path(env["GIT_ASKPASS"])

        assert askpass_path.exists()
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GITHUB_TOKEN_AEJ"] == "super-secret-token"
        assert "super-secret-token" not in askpass_path.read_text(encoding="utf-8")
        assert "super-secret-token" not in " ".join(args)

    module._clone_repo(
        "https://github.com/kingfink/analytics-engineering-jobs.git",
        tmp_path / "analytics-engineering-jobs",
        github_token="super-secret-token",
        run_command=fake_run,
    )

    assert calls[0]["args"] == [
        "git",
        "clone",
        "https://github.com/kingfink/analytics-engineering-jobs.git",
        str(tmp_path / "analytics-engineering-jobs"),
    ]
    assert calls[0]["check"] is True


def test_bigquery_storage_dependency_is_available_in_package_and_modal_image() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    tree = ast.parse(MODAL_ENTRYPOINT_PATH.read_text(encoding="utf-8"))

    assert "google-cloud-bigquery-storage==2.37.0" in dependencies
    assert "pip_install_from_pyproject" in _chained_call_names(_modal_image_expression(tree))
    assert not _modal_pip_install_packages(tree)


def test_modal_image_adds_local_package_source() -> None:
    tree = ast.parse(MODAL_ENTRYPOINT_PATH.read_text(encoding="utf-8"))
    image_calls = _chained_call_names(_modal_image_expression(tree))

    assert image_calls.index("apt_install") < image_calls.index("pip_install_from_pyproject")
    assert "add_local_python_source" in image_calls


def test_configure_logging_lowers_existing_modal_handler_to_info(monkeypatch) -> None:
    module = _load_modal_entrypoint(monkeypatch)
    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)
    handler = logging.Handler()
    handler.setLevel(logging.WARNING)

    try:
        root.handlers = [handler]
        root.setLevel(logging.WARNING)

        module._configure_logging()

        assert root.level == logging.INFO
        assert handler.level == logging.INFO
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)


def _modal_image_expression(tree: ast.Module) -> ast.AST:
    return next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "image"
    )


def _chained_call_names(node: ast.AST) -> list[str]:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return []

    return [*_chained_call_names(node.func.value), node.func.attr]


def _modal_pip_install_packages(tree: ast.Module) -> list[str]:
    packages = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "pip_install"
        ):
            packages.extend(ast.literal_eval(arg) for arg in node.args)
    return packages


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


def _load_modal_entrypoint(monkeypatch):
    monkeypatch.setitem(sys.modules, "modal", _FakeModal)
    spec = importlib.util.spec_from_file_location(
        "_modal_app_test",
        MODAL_ENTRYPOINT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeImage:
    @classmethod
    def debian_slim(cls, **kwargs):
        return cls()

    def apt_install(self, *packages):
        return self

    def pip_install(self, *packages):
        return self

    def pip_install_from_pyproject(self, *args, **kwargs):
        return self

    def add_local_dir(self, *args, **kwargs):
        return self

    def add_local_python_source(self, *args, **kwargs):
        return self


class _FakeSecret:
    @classmethod
    def from_name(cls, name):
        return cls()


class _FakeApp:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def function(self, **kwargs):
        def decorator(func):
            return func

        return decorator

    def local_entrypoint(self):
        def decorator(func):
            return func

        return decorator


class _FakeCron:
    def __init__(self, *args, **kwargs) -> None:
        pass


class _FakeModal:
    App = _FakeApp
    Cron = _FakeCron
    Image = _FakeImage
    Secret = _FakeSecret
