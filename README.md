# aej-dlt

Analytics Engineering Jobs markdown content -> BigQuery via
[`dlt`](https://dlthub.com/), scheduled on [Modal](https://modal.com/).

The pipeline loads raw source content from
[`kingfink/analytics-engineering-jobs`](https://github.com/kingfink/analytics-engineering-jobs).
Markdown extraction comes from the shared
[`tailor-made-dlt-sources`](https://github.com/kingfink/dlt-sources) package, so
this repo only owns the Analytics Engineering Jobs resource globs, BigQuery
destination wiring, and Modal runtime.

The pipeline currently loads `jobs` and `organizations`. Both tables use the
same row shape:

- `file_path`
- `frontmatter` as a BigQuery JSON column
- `content` as everything after the frontmatter block
- `created_at` from the oldest git history entry for the file
- `modified_at` from the newest git history entry for the file
- `modified_at_cursor` as an internal incremental cursor

Provider or filesystem mtimes are intentionally ignored because fresh clones
would make checkout time look like content change time.

## Public visibility

This repository is public for source visibility only. It is not maintained as a
community project and is not accepting outside contributions, pull requests,
issues, or support requests. No license is provided.

## Local dev

Prereqs:

- `uv`
- BigQuery destination configuration for your own project and dataset

```bash
uv sync --extra dev
```

Set destination configuration in the environment, then point the local runner at
a checkout of the source repo:

```bash
export BIGQUERY_PROJECT=<gcp-project-id>
export BIGQUERY_DATASET=aej_dev_$USER
export BIGQUERY_LOCATION=US

uv run python modal_app.py --repo-root /path/to/analytics-engineering-jobs
uv run python modal_app.py --repo-root /path/to/analytics-engineering-jobs --full-refresh
```

Authenticate locally with Application Default Credentials or
`GOOGLE_APPLICATION_CREDENTIALS`.

The sync uses `file_path` as the primary key, git-derived `modified_at_cursor`
as the incremental cursor, and dlt `merge` write disposition. Deletions are not
hard-deleted in v1.

## Modal

The Modal app expects secrets for GitHub source-repo access, BigQuery
destination configuration, and BigQuery service account credentials. See
`modal_app.py` for the environment variable names.

```bash
uv run modal deploy modal_app.py
uv run modal run modal_app.py::sync
uv run modal run modal_app.py::sync --full-refresh
```

The scheduled Modal function clones the source repository fresh on each run so
git-derived content timestamps are stable.

## Layout

| Path | What it does |
| --- | --- |
| `tailor_made_dlt_sources.git_repo_markdown_files` | Shared markdown filesystem source and git timestamp extraction. |
| `aej_dlt/sync_bigquery.py` | Builds the AEJ markdown resources and runs the BigQuery dlt pipeline. |
| `modal_app.py` | Modal app, cron entry point, and local CLI wrapper. |
| `tests/` | Pipeline, Modal entrypoint, packaging, and CI contract tests. |
