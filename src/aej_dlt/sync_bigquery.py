"""Sync repo-backed jobs and organizations into BigQuery with dlt."""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

from tailor_made_dlt_sources.git_repo_markdown_files import (
    build_dlt_resources as build_markdown_dlt_resources,
)

PIPELINE_NAME = "aej_repo_content"
BIGQUERY_PRIVATE_KEY_ENV = "DESTINATION__BIGQUERY__CREDENTIALS__PRIVATE_KEY"

AEJ_RESOURCE_GLOBS = {
    "jobs": "docs/jobs/**/*.md",
    "organizations": "docs/organizations/*.md",
}


def sync_bigquery(
    repo_root: Path = Path("."),
    *,
    dlt_module=None,
    filesystem_resource=None,
    timestamp_resolver=None,
    full_refresh: bool = False,
):
    """Sync repo markdown content from ``repo_root`` to BigQuery."""
    return sync_rows(
        repo_root=repo_root,
        dlt_module=dlt_module,
        filesystem_resource=filesystem_resource,
        timestamp_resolver=timestamp_resolver,
        full_refresh=full_refresh,
    )


def sync_rows(
    *,
    repo_root: Path,
    dlt_module=None,
    filesystem_resource=None,
    timestamp_resolver=None,
    full_refresh: bool = False,
):
    """Sync repo markdown rows to BigQuery.

    ``dlt_module`` is injectable so tests can verify configuration without
    importing dlt or contacting BigQuery.
    """
    dlt_module = dlt_module or importlib.import_module("dlt")
    _normalize_bigquery_private_key_env()
    project = _required_env("BIGQUERY_PROJECT")
    dataset = _required_env("BIGQUERY_DATASET")
    location = os.environ.get("BIGQUERY_LOCATION")

    dlt_module.config["destination.bigquery.project_id"] = project
    if location:
        dlt_module.config["destination.bigquery.location"] = location

    pipeline = dlt_module.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination="bigquery",
        dataset_name=dataset,
    )
    run_kwargs = {"loader_file_format": "jsonl"}
    if full_refresh:
        run_kwargs["refresh"] = "drop_data"

    return pipeline.run(
        build_dlt_resources(
            dlt_module,
            repo_root=repo_root,
            filesystem_resource=filesystem_resource or _filesystem_resource(),
            timestamp_resolver=timestamp_resolver,
        ),
        **run_kwargs,
    )


def build_dlt_resources(
    dlt_module,
    *,
    repo_root: Path,
    filesystem_resource,
    timestamp_resolver=None,
):
    """Return AEJ markdown resources for incremental merge loading."""
    return build_markdown_dlt_resources(
        dlt_module,
        repo_root=repo_root,
        resource_globs=AEJ_RESOURCE_GLOBS,
        filesystem_resource=filesystem_resource,
        timestamp_resolver=timestamp_resolver,
    )


def _filesystem_resource():
    return importlib.import_module("dlt.sources.filesystem").filesystem


def _normalize_bigquery_private_key_env() -> None:
    private_key = os.environ.get(BIGQUERY_PRIVATE_KEY_ENV)
    if private_key and "\\n" in private_key:
        os.environ[BIGQUERY_PRIVATE_KEY_ENV] = private_key.replace("\\n", "\n")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
    args = parser.parse_args(argv)

    load_info = sync_bigquery(args.repo_root, full_refresh=args.full_refresh)
    print(load_info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
