"""Sync repo-backed jobs and organizations into BigQuery with dlt."""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path

from aej_dlt.warehouse import GitTimestampResolver, build_file_item_rows

PIPELINE_NAME = "aej_repo_content"
INCREMENTAL_INITIAL_VALUE = "1970-01-01T00:00:00+00:00"

RESOURCE_COLUMNS = {
    "file_path": {"data_type": "text"},
    "frontmatter": {"data_type": "json"},
    "content": {"data_type": "text"},
    "created_at": {"data_type": "timestamp"},
    "modified_at": {"data_type": "timestamp"},
}


def sync_bigquery(
    repo_root: Path = Path("."),
    *,
    dlt_module=None,
    filesystem_resource=None,
    timestamp_resolver=None,
):
    """Sync repo markdown content from ``repo_root`` to BigQuery."""
    return sync_rows(
        repo_root=repo_root,
        dlt_module=dlt_module,
        filesystem_resource=filesystem_resource,
        timestamp_resolver=timestamp_resolver,
    )


def sync_rows(
    *,
    repo_root: Path,
    dlt_module=None,
    filesystem_resource=None,
    timestamp_resolver=None,
):
    """Sync repo markdown rows to BigQuery.

    ``dlt_module`` is injectable so tests can verify configuration without
    importing dlt or contacting BigQuery.
    """
    dlt_module = dlt_module or importlib.import_module("dlt")
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
    return pipeline.run(
        build_dlt_resources(
            dlt_module,
            repo_root=repo_root,
            filesystem_resource=filesystem_resource or _filesystem_resource(),
            timestamp_resolver=timestamp_resolver,
        ),
        loader_file_format="jsonl",
    )


def build_dlt_resources(
    dlt_module,
    *,
    repo_root: Path,
    filesystem_resource,
    timestamp_resolver=None,
):
    """Return dlt resources for incremental merge loading."""
    repo_root = Path(repo_root).resolve()
    resolver = timestamp_resolver or GitTimestampResolver(repo_root)
    return [
        _incremental_resource(
            dlt_module,
            "jobs",
            filesystem_resource(
                bucket_url=repo_root.as_uri(),
                file_glob="docs/jobs/**/*.md",
            ),
            resolver,
        ),
        _incremental_resource(
            dlt_module,
            "organizations",
            filesystem_resource(
                bucket_url=repo_root.as_uri(),
                file_glob="docs/organizations/*.md",
            ),
            resolver,
        ),
    ]


def _incremental_resource(dlt_module, table_name: str, file_items, timestamp_resolver):
    @dlt_module.resource(
        name=table_name,
        primary_key="file_path",
        write_disposition="merge",
        columns=RESOURCE_COLUMNS,
    )
    def markdown_rows(
        modified_at=dlt_module.sources.incremental(  # noqa: B008
            "modified_at",
            initial_value=INCREMENTAL_INITIAL_VALUE,
            row_order="asc",
        ),
    ):
        del modified_at
        ordered_rows = sorted(
            build_file_item_rows(file_items, timestamp_resolver),
            key=lambda row: (str(row["modified_at"]), str(row["file_path"])),
        )
        yield from ordered_rows

    return markdown_rows


def _filesystem_resource():
    return importlib.import_module("dlt.sources.filesystem").filesystem


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
    args = parser.parse_args(argv)

    load_info = sync_bigquery(args.repo_root)
    print(load_info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
