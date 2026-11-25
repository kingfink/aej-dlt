"""Load Stripe objects into AEJ's BigQuery destination via dlt's verified Stripe source."""

from __future__ import annotations

import importlib
import os

from aej_dlt.stripe_analytics import incremental_stripe_source, stripe_source
from aej_dlt.sync_bigquery import (
    _normalize_bigquery_private_key_env,
    _required_env,
)

PIPELINE_NAME = "aej_stripe"
DEFAULT_DATASET = "stripe"

# Stripe objects are mutable and have no "updated" field, so the verified source can only
# reload them in full. Every run replaces these tables with the current state.
SNAPSHOT_ENDPOINTS = (
    "Account",
    "Charge",
    "Coupon",
    "Customer",
    "Dispute",
    "Invoice",
    "PaymentIntent",
    "Payout",
    "Price",
    "Product",
    "Refund",
    "Subscription",
)
# Immutable objects load incrementally on ``created`` and are appended by ``id``.
INCREMENTAL_ENDPOINTS = ("BalanceTransaction", "Event")


def sync_stripe(
    *,
    dlt_module=None,
    snapshot_source_factory=stripe_source,
    incremental_source_factory=incremental_stripe_source,
    full_refresh: bool = False,
):
    """Load Stripe objects into the raw BigQuery dataset.

    Immutable balance transactions and events are loaded incrementally by
    ``created``, so the first run backfills everything Stripe returns and reruns
    append only new records. Mutable objects are replaced in full on every run.
    """
    dlt_module = dlt_module or importlib.import_module("dlt")
    _normalize_bigquery_private_key_env()
    project = _required_env("BIGQUERY_PROJECT")
    location = os.environ.get("BIGQUERY_LOCATION")
    api_key = _required_env("STRIPE_API_KEY")

    dlt_module.config["destination.bigquery.project_id"] = project
    if location:
        dlt_module.config["destination.bigquery.location"] = location

    pipeline = dlt_module.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination="bigquery",
        dataset_name=os.environ.get("STRIPE_BIGQUERY_DATASET", DEFAULT_DATASET),
    )
    run_kwargs = {"loader_file_format": "jsonl"}
    if full_refresh:
        run_kwargs["refresh"] = "drop_data"

    sources = [
        snapshot_source_factory(endpoints=SNAPSHOT_ENDPOINTS, stripe_secret_key=api_key),
        incremental_source_factory(endpoints=INCREMENTAL_ENDPOINTS, stripe_secret_key=api_key),
    ]
    return pipeline.run(sources, **run_kwargs)
