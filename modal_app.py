"""Analytics Engineering Jobs -> BigQuery dlt pipeline.

Cron + Modal:
    modal deploy modal_app.py
    modal run modal_app.py::sync
    modal run modal_app.py::sync --full-refresh

Local dev:
    python modal_app.py --repo-root /path/to/analytics-engineering-jobs
    python modal_app.py --repo-root /path/to/analytics-engineering-jobs --full-refresh
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import modal

APP_NAME = "aej-dlt"
SECRET_NAME = "aej-dlt-bq-sync"
NETLIFY_SECRET_NAME = "aej-dlt-netlify"
HEALTHCHECKS_SECRET_NAME = "aej-dlt-healthchecks"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN_AEJ"
DEFAULT_REPO_URL = "https://github.com/kingfink/analytics-engineering-jobs.git"
DEFAULT_REF = "master"
SECRETS = [
    modal.Secret.from_name(SECRET_NAME),
    modal.Secret.from_name(NETLIFY_SECRET_NAME),
    modal.Secret.from_name(HEALTHCHECKS_SECRET_NAME),
]
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_python_source("aej_dlt")
)

app = modal.App(APP_NAME)


def _configure_logging(level: int = logging.INFO) -> None:
    """Ensure Modal and local runs emit info-level pipeline diagnostics."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format=LOG_FORMAT)
        return

    root.setLevel(level)
    for handler in root.handlers:
        if handler.level == logging.NOTSET or handler.level > level:
            handler.setLevel(level)


@app.function(
    image=image,
    schedule=modal.Cron("45 5,11,17,23 * * *", timezone="UTC"),
    secrets=SECRETS,
    timeout=3600,
)
def sync(full_refresh: bool = False):
    """Load repository content and Netlify submissions into BigQuery."""
    from aej_dlt.healthcheck import run_with_healthcheck

    _configure_logging()
    return run_with_healthcheck(lambda: _sync_from_fresh_clone(full_refresh=full_refresh))


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

        return _sync_all(repo_path, full_refresh=full_refresh)


def _sync_all(repo_root: Path, *, full_refresh: bool):
    from aej_dlt.netlify_forms import sync_netlify_forms
    from aej_dlt.sync_bigquery import sync_bigquery

    return {
        "repo_content": str(sync_bigquery(repo_root, full_refresh=full_refresh)),
        "netlify_forms": str(sync_netlify_forms(full_refresh=full_refresh)),
    }


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local dev run.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root containing docs/jobs and docs/organizations.",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Truncate loaded tables and reset incremental state before syncing.",
    )
    args = parser.parse_args()

    _configure_logging()

    print(_sync_all(args.repo_root, full_refresh=args.full_refresh))
