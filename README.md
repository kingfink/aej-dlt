# aej-dlt

`aej-dlt` loads raw source content from
[`kingfink/analytics-engineering-jobs`](https://github.com/kingfink/analytics-engineering-jobs)
into BigQuery with [`dlt`](https://dlthub.com/).

Markdown extraction is provided by
[`tailor-made-dlt-sources`](https://github.com/kingfink/dlt-sources). This repo
keeps only the Analytics Engineering Jobs-specific `resource_globs`,
BigQuery destination wiring, and Modal runtime.

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

## Public Visibility

This repository is public for source visibility only. It is not maintained as a
community project and is not accepting outside contributions, pull requests,
issues, or support requests. No license is provided.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

## Local Sync

Set BigQuery destination configuration in the environment, then point the CLI at
a local checkout of the source repo:

```bash
export BIGQUERY_PROJECT=<gcp-project-id>
export BIGQUERY_DATASET=<dataset-name>
export BIGQUERY_LOCATION=US

aej-dlt --repo-root /path/to/analytics-engineering-jobs
aej-dlt --repo-root /path/to/analytics-engineering-jobs --full-refresh
```

Authenticate locally with Application Default Credentials or
`GOOGLE_APPLICATION_CREDENTIALS`.

The sync uses `file_path` as the primary key, git-derived `modified_at_cursor`
as the incremental cursor, and dlt `merge` write disposition. Deletions are not
hard-deleted in v1.

## Modal

The Modal app is defined in `src/aej_dlt/modal_sync_bigquery.py`. It clones the
source repo fresh on every run, then calls the same sync code.

```bash
modal deploy src/aej_dlt/modal_sync_bigquery.py
modal run src/aej_dlt/modal_sync_bigquery.py
modal run src/aej_dlt/modal_sync_bigquery.py --full-refresh
```

The deployed app expects Modal secrets for GitHub source-repo access, BigQuery
destination configuration, and BigQuery service account credentials.
