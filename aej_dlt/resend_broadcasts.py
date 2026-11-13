"""Load the reusable Resend broadcasts source into AEJ's BigQuery destination."""

from __future__ import annotations

import importlib
import os

from tailor_made_dlt_sources.resend import resend_source

from aej_dlt.sync_bigquery import (
    _normalize_bigquery_private_key_env,
    _required_env,
)

PIPELINE_NAME = "aej_resend_broadcasts"
DEFAULT_DATASET = "resend"


def sync_resend_broadcasts(
    *,
    dlt_module=None,
    source_factory=resend_source,
    full_refresh: bool = False,
):
    """Load newsletter broadcast content into the raw BigQuery dataset.

    The resource merges on ``broadcast_id``, so the first run backfills every
    sent broadcast and reruns pick up new broadcasts and content edits
    without duplicating rows.
    """
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
        dataset_name=os.environ.get("RESEND_BIGQUERY_DATASET", DEFAULT_DATASET),
    )
    run_kwargs = {"loader_file_format": "jsonl"}
    if full_refresh:
        run_kwargs["refresh"] = "drop_data"

    return pipeline.run(
        source_factory(api_key=_required_env("RESEND_API_KEY")),
        **run_kwargs,
    )
