# CI/CD Design

## Goal

Add GitHub Actions automation that validates every pull request and deploys the Modal app from `master` after validation passes.

## Scope

The workflow will:

- Run on pull requests targeting `master`.
- Run on pushes to `master`.
- Install Python 3.11 and the package with dev dependencies.
- Run `ruff check .`, `ruff format --check .`, and `pytest`.
- Deploy `src/aej_dlt/modal_sync_bigquery.py` to Modal only for pushes to `master`.

The workflow will not deploy unmerged pull request branches because the current Modal app is a shared scheduled deployment.

## Secrets

GitHub Actions must provide:

- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`

The deployed Modal app will continue to use the existing `bigquery-sync` Modal secret for BigQuery credentials.

## Testing

Add a repository test that parses the workflow file and verifies the required triggers, validation commands, Modal secrets, and deploy command.
