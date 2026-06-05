"""Tests for the GitHub Actions CI/CD workflow contract."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/ci-cd.yml")


def test_ci_cd_workflow_validates_prs_and_deploys_master() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))

    assert workflow["on"] == {
        "pull_request": {"branches": ["master"]},
        "push": {"branches": ["master"]},
    }
    assert workflow["permissions"] == {"contents": "read"}

    validate = workflow["jobs"]["validate"]
    assert validate["runs-on"] == "ubuntu-latest"
    assert validate["steps"][1]["uses"] == "actions/setup-python@v5"
    assert validate["steps"][1]["with"]["python-version"] == "3.11"

    commands = [step.get("run") for step in validate["steps"] if "run" in step]
    assert 'python -m pip install --upgrade pip\npython -m pip install -e ".[dev]"\n' in commands
    assert "python -m ruff check .\n" in commands
    assert "python -m ruff format --check .\n" in commands
    assert "python -m pytest\n" in commands

    deploy = workflow["jobs"]["deploy-modal"]
    assert deploy["needs"] == "validate"
    assert deploy["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/master'"
    assert deploy["env"]["MODAL_TOKEN_ID"] == "${{ secrets.MODAL_TOKEN_ID }}"
    assert deploy["env"]["MODAL_TOKEN_SECRET"] == "${{ secrets.MODAL_TOKEN_SECRET }}"

    deploy_commands = [step.get("run") for step in deploy["steps"] if "run" in step]
    assert "modal deploy src/aej_dlt/modal_sync_bigquery.py\n" in deploy_commands
