"""Tests for the GitHub Actions CI/CD workflow contract."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/ci-cd.yml")


def test_ci_cd_workflow_uses_uv_and_deploys_master() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    assert workflow["on"] == {
        "pull_request": {"branches": ["master"]},
        "push": {"branches": ["master"]},
        "workflow_dispatch": None,
    }
    assert workflow["permissions"] == {"contents": "read"}

    validate = workflow["jobs"]["validate"]
    assert validate["runs-on"] == "ubuntu-latest"
    assert validate["if"] == (
        "github.event_name != 'pull_request' "
        "|| github.event.pull_request.head.repo.full_name == github.repository"
    )
    assert validate["steps"][1]["uses"] == "astral-sh/setup-uv@v6"
    assert validate["steps"][1]["with"] == {"enable-cache": True}

    commands = [step.get("run") for step in validate["steps"] if "run" in step]
    assert "uv sync --extra dev --frozen" in commands
    assert "uv run ruff check ." in commands
    assert "uv run ruff format --check ." in commands
    assert "uv run pytest" in commands

    deploy = workflow["jobs"]["deploy-modal"]
    assert deploy["needs"] == "validate"
    assert deploy["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/master'"
    assert deploy["env"]["MODAL_TOKEN_ID"] == "${{ secrets.MODAL_TOKEN_ID }}"
    assert deploy["env"]["MODAL_TOKEN_SECRET"] == "${{ secrets.MODAL_TOKEN_SECRET }}"

    deploy_commands = [step.get("run") for step in deploy["steps"] if "run" in step]
    assert "uv sync --frozen" in deploy_commands
    assert "uv run modal deploy modal_app.py" in deploy_commands
