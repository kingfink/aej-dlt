# aej-dlt

`aej-dlt` loads raw source content from
[`kingfink/analytics-engineering-jobs`](https://github.com/kingfink/analytics-engineering-jobs)
into BigQuery with [`dlt`](https://dlthub.com/).

The pipeline currently loads two tables:

- `jobs`
- `organizations`

Both tables use the same row shape:

- `file_path`
- `frontmatter` as a BigQuery JSON column
- `content` as everything after the frontmatter block
- `created_at` from the oldest git history entry for the file
- `modified_at` from the newest git history entry for the file

Source files are discovered and opened with dlt's filesystem source. Provider
or filesystem mtimes are intentionally ignored because fresh clones would make
checkout time look like content change time.

## Local Development

Install the package and dev dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

## CI/CD

GitHub Actions runs linting, formatting, and tests on pull requests targeting
`master` and on pushes to `master`.

Pushes to `master` deploy the Modal app after validation passes. Configure these
GitHub repository secrets before relying on automated deploys:

- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`

The deployed Modal app still reads BigQuery credentials and sync settings from
the `aej-dlt-bq-sync` Modal secret described below.

## Local Sync

Clone or update the source repo, then run:

```bash
export BIGQUERY_PROJECT=my-gcp-project
export BIGQUERY_DATASET=analytics_engineering_jobs
export BIGQUERY_LOCATION=US

aej-dlt --repo-root /path/to/analytics-engineering-jobs
```

Authenticate locally with Application Default Credentials or
`GOOGLE_APPLICATION_CREDENTIALS`.

The sync uses `file_path` as the primary key, git-derived `modified_at` as the
incremental cursor, and dlt `merge` write disposition so changed files are
upserted on later runs. Deletions are not hard-deleted in v1.

To truncate the destination tables and reset incremental state before syncing:

```bash
aej-dlt --repo-root /path/to/analytics-engineering-jobs --full-refresh
```

## Modal

The Modal app is defined in `src/aej_dlt/modal_sync_bigquery.py`. It clones the
source repo fresh on every run, then calls the same sync code.

Create an `aej-dlt-bq-sync` Modal secret with sync settings and BigQuery
destination credentials:

- `BIGQUERY_PROJECT`
- `BIGQUERY_DATASET`
- optional `BIGQUERY_LOCATION`
- optional `AEJ_REPO_URL`, defaults to `https://github.com/kingfink/analytics-engineering-jobs.git`
- optional `AEJ_REF`, defaults to `master`
- `GITHUB_TOKEN_AEJ`, a GitHub token with read-only contents access to the source repo
- `DESTINATION__BIGQUERY__CREDENTIALS__PROJECT_ID`
- `DESTINATION__BIGQUERY__CREDENTIALS__CLIENT_EMAIL`
- `DESTINATION__BIGQUERY__CREDENTIALS__PRIVATE_KEY`

For a Google service account JSON file, copy the individual field values into
the Modal secret. Use the JSON's `private_key` value for
`DESTINATION__BIGQUERY__CREDENTIALS__PRIVATE_KEY`, not the full JSON document.

Deploy the scheduled sync:

```bash
modal deploy src/aej_dlt/modal_sync_bigquery.py
```

Run an on-demand sync without adding another deployed Modal function:

```bash
modal run src/aej_dlt/modal_sync_bigquery.py
```

Run an on-demand full refresh:

```bash
modal run src/aej_dlt/modal_sync_bigquery.py --full-refresh
```
