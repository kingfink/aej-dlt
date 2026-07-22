"""Load the reusable Netlify Forms source into AEJ's BigQuery destination."""

from __future__ import annotations

import importlib
import os

from tailor_made_dlt_sources.netlify_forms import netlify_forms_source

from aej_dlt.sync_bigquery import (
    _normalize_bigquery_private_key_env,
    _required_env,
)

PIPELINE_NAME = "aej_netlify_forms"
DEFAULT_DATASET = "netlify"


def sync_netlify_forms(
    *,
    dlt_module=None,
    source_factory=netlify_forms_source,
    full_refresh: bool = False,
):
    """Load verified Netlify submissions into the raw BigQuery dataset."""
    dlt_module = dlt_module or importlib.import_module("dlt")
    _normalize_bigquery_private_key_env()
    project = _required_env("BIGQUERY_PROJECT")
    location = os.environ.get("BIGQUERY_LOCATION")

    dlt_module.config["destination.bigquery.project_id"] = project
    if location:
        dlt_module.config["destination.bigquery.location"] = location

    pipeline = dlt_module.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination="bigquery",
        dataset_name=os.environ.get("NETLIFY_BIGQUERY_DATASET", DEFAULT_DATASET),
    )
    run_kwargs = {"loader_file_format": "jsonl"}
    if full_refresh:
        run_kwargs["refresh"] = "drop_data"

    return pipeline.run(
        source_factory(
            access_token=_required_env("NETLIFY_ACCESS_TOKEN"),
            site_id=_required_env("NETLIFY_SITE_ID"),
        ),
        **run_kwargs,
    )
