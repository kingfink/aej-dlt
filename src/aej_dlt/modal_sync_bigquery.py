"""Modal entrypoint for syncing Analytics Engineering Jobs content to BigQuery."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import modal

APP_NAME = "aej-bigquery-sync"
SECRET_NAME = "aej-dlt-bq-sync"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN_AEJ"
DEFAULT_REPO_URL = "https://github.com/kingfink/analytics-engineering-jobs.git"
DEFAULT_REF = "master"
SOURCE_ROOT = Path(__file__).resolve().parent.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "dlt[bigquery]==1.26.0",
        "google-cloud-bigquery-storage==2.37.0",
        "modal==1.2.5",
        "pyyaml==6.0.2",
    )
    .add_local_dir(
        SOURCE_ROOT / "aej_dlt",
        remote_path="/root/aej_dlt",
        ignore=["__pycache__/**", "*.pyc"],
    )
)

app = modal.App(APP_NAME, image=image)


@app.function(
    schedule=modal.Cron("0 6 * * *", timezone="America/New_York"),
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    timeout=3600,
)
def sync(full_refresh: bool = False):
    """Run the scheduled BigQuery sync from a fresh clone."""
    return _sync_from_fresh_clone(full_refresh=full_refresh)


@app.local_entrypoint()
def main(full_refresh: bool = False):
    print(sync.remote(full_refresh=full_refresh))


def _sync_from_fresh_clone(*, full_refresh: bool):
    repo_url = os.environ.get("AEJ_REPO_URL", DEFAULT_REPO_URL)
    ref = os.environ.get("AEJ_REF", DEFAULT_REF)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "analytics-engineering-jobs"
        _clone_repo(repo_url, repo_path, github_token=os.environ.get(GITHUB_TOKEN_ENV))
        subprocess.run(["git", "checkout", ref], cwd=repo_path, check=True)

        from aej_dlt.sync_bigquery import sync_bigquery

        return str(sync_bigquery(repo_path, full_refresh=full_refresh))


def _clone_repo(
    repo_url: str,
    repo_path: Path,
    *,
    github_token: str | None = None,
    run_command=subprocess.run,
) -> None:
    if not github_token:
        run_command(["git", "clone", repo_url, str(repo_path)], check=True)
        return

    with tempfile.TemporaryDirectory() as askpass_dir:
        askpass_path = Path(askpass_dir) / "github-askpass.sh"
        askpass_path.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  *Username*) printf '%s\\n' x-access-token ;;\n"
            "  *) printf '%s\\n' \"$GITHUB_TOKEN_AEJ\" ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        askpass_path.chmod(0o700)

        env = os.environ.copy()
        env.update(
            {
                "GIT_ASKPASS": str(askpass_path),
                "GIT_TERMINAL_PROMPT": "0",
                GITHUB_TOKEN_ENV: github_token,
            }
        )
        run_command(["git", "clone", repo_url, str(repo_path)], check=True, env=env)
