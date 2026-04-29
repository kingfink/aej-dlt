"""Modal entrypoint for syncing Analytics Engineering Jobs content to BigQuery."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import modal

APP_NAME = "aej-bigquery-sync"
SECRET_NAME = "bigquery-sync"
DEFAULT_REPO_URL = "https://github.com/kingfink/analytics-engineering-jobs.git"
DEFAULT_REF = "master"
SOURCE_ROOT = Path(__file__).resolve().parent.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install("dlt[bigquery]==1.26.0", "modal==1.2.5", "pyyaml==6.0.2")
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
def scheduled_sync():
    """Run the scheduled BigQuery sync from a fresh clone."""
    return _sync_from_fresh_clone()


@app.function(
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    timeout=3600,
)
def sync_now():
    """Run the BigQuery sync on demand from a fresh clone."""
    return _sync_from_fresh_clone()


@app.local_entrypoint()
def main():
    print(sync_now.remote())


def _sync_from_fresh_clone():
    repo_url = os.environ.get("AEJ_REPO_URL", DEFAULT_REPO_URL)
    ref = os.environ.get("AEJ_REF", DEFAULT_REF)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "analytics-engineering-jobs"
        subprocess.run(["git", "clone", repo_url, str(repo_path)], check=True)
        subprocess.run(["git", "checkout", ref], cwd=repo_path, check=True)

        from aej_dlt.sync_bigquery import sync_bigquery

        return str(sync_bigquery(repo_path))
