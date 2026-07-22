"""Tests for the upstream dlt-sources dependency contract."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

MODAL_ENTRYPOINT_PATH = Path("modal_app.py")
PYPROJECT_PATH = Path("pyproject.toml")
SYNC_BIGQUERY_PATH = Path("aej_dlt/sync_bigquery.py")

DLT_SOURCES_REQUIREMENT = (
    "tailor-made-dlt-sources @ git+https://github.com/kingfink/dlt-sources@v0.2.0"
)
GIT_REPO_SOURCE_IMPORT = "tailor_made_dlt_sources.git_repo_markdown_files"
NETLIFY_SOURCE_IMPORT = "tailor_made_dlt_sources.netlify_forms"


def test_package_and_modal_image_pin_tailor_made_dlt_sources_release() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

    assert DLT_SOURCES_REQUIREMENT in pyproject["project"]["dependencies"]
    assert pyproject["tool"]["hatch"]["metadata"]["allow-direct-references"] is True
    assert not _modal_pip_install_packages()


def test_sync_imports_git_repo_markdown_files_source_package() -> None:
    tree = ast.parse(SYNC_BIGQUERY_PATH.read_text(encoding="utf-8"))

    imports = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    ]

    assert GIT_REPO_SOURCE_IMPORT in imports


def test_netlify_sync_imports_netlify_forms_source_package() -> None:
    tree = ast.parse(Path("aej_dlt/netlify_forms.py").read_text(encoding="utf-8"))

    imports = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    ]

    assert NETLIFY_SOURCE_IMPORT in imports


def _modal_pip_install_packages() -> list[str]:
    tree = ast.parse(MODAL_ENTRYPOINT_PATH.read_text(encoding="utf-8"))
    packages = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "pip_install"
        ):
            packages.extend(ast.literal_eval(arg) for arg in node.args)
    return packages
