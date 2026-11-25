"""Tests for AEJ's Stripe BigQuery pipeline."""

from __future__ import annotations

import pytest

from aej_dlt import stripe_data
from aej_dlt.stripe_analytics import helpers, incremental_stripe_source, stripe_source
from aej_dlt.stripe_data import sync_stripe


def test_sync_configures_stripe_dataset_and_sources(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("BIGQUERY_LOCATION", "US")
    monkeypatch.setenv("STRIPE_API_KEY", "rk_test_secret")
    dlt = FakeDlt()
    calls = []

    load_info = sync_stripe(
        dlt_module=dlt,
        snapshot_source_factory=lambda **kw: calls.append(("snapshot", kw)) or "snap",
        incremental_source_factory=lambda **kw: calls.append(("incremental", kw)) or "inc",
    )

    assert load_info == "loaded"
    assert dlt.config == {
        "destination.bigquery.project_id": "warehouse-project",
        "destination.bigquery.location": "US",
    }
    assert dlt.pipeline_call == {
        "pipeline_name": "aej_stripe",
        "destination": "bigquery",
        "dataset_name": "stripe",
    }
    assert calls == [
        (
            "snapshot",
            {"endpoints": stripe_data.SNAPSHOT_ENDPOINTS, "stripe_secret_key": "rk_test_secret"},
        ),
        (
            "incremental",
            {
                "endpoints": stripe_data.INCREMENTAL_ENDPOINTS,
                "stripe_secret_key": "rk_test_secret",
            },
        ),
    ]
    assert dlt.pipeline_instance.run_call == {
        "data": ["snap", "inc"],
        "loader_file_format": "jsonl",
    }


def test_sync_can_request_drop_data_refresh(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("STRIPE_API_KEY", "rk_test_secret")
    dlt = FakeDlt()

    sync_stripe(
        dlt_module=dlt,
        snapshot_source_factory=lambda **kw: "snap",
        incremental_source_factory=lambda **kw: "inc",
        full_refresh=True,
    )

    assert dlt.pipeline_instance.run_call["refresh"] == "drop_data"


def test_sync_uses_dataset_override(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("STRIPE_API_KEY", "rk_test_secret")
    monkeypatch.setenv("STRIPE_BIGQUERY_DATASET", "stripe_dev")
    dlt = FakeDlt()

    sync_stripe(
        dlt_module=dlt,
        snapshot_source_factory=lambda **kw: "snap",
        incremental_source_factory=lambda **kw: "inc",
    )

    assert dlt.pipeline_call["dataset_name"] == "stripe_dev"


def test_sync_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)

    with pytest.raises(Exception, match="STRIPE_API_KEY"):
        sync_stripe(dlt_module=FakeDlt())


def test_endpoints_resolve_to_stripe_list_resources() -> None:
    import stripe

    for name in (*stripe_data.SNAPSHOT_ENDPOINTS, *stripe_data.INCREMENTAL_ENDPOINTS):
        assert callable(getattr(getattr(stripe, name), "list", None)), name


def test_snapshot_resources_replace_and_incremental_resources_append_by_id() -> None:
    snapshot = stripe_source(endpoints=("Customer",), stripe_secret_key="k")
    incremental = incremental_stripe_source(endpoints=("Event",), stripe_secret_key="k")

    assert snapshot.resources["Customer"].write_disposition == "replace"
    assert incremental.resources["Event"].write_disposition == "append"
    assert incremental.resources["Event"].compute_table_schema()["columns"]["id"]["primary_key"]


def test_pagination_follows_has_more_and_reports_failures(monkeypatch) -> None:
    pages = [
        {"data": [{"id": "a"}, {"id": "b"}], "has_more": True},
        {"data": [{"id": "c"}], "has_more": False},
    ]
    cursors = []

    def fake_get(resource, start_date=None, end_date=None, **kwargs):
        cursors.append(kwargs["starting_after"])
        return pages.pop(0)

    monkeypatch.setattr(helpers, "stripe_get_data", fake_get)

    assert list(helpers.pagination("Customer")) == [[{"id": "a"}, {"id": "b"}], [{"id": "c"}]]
    assert cursors == [None, "b"]

    def failing_get(*args, **kwargs):
        raise RuntimeError("stripe down")

    monkeypatch.setattr(helpers, "stripe_get_data", failing_get)
    with pytest.raises(RuntimeError, match="stripe down"):
        list(helpers.pagination("Customer"))


class FakePipeline:
    def __init__(self) -> None:
        self.run_call = None

    def run(self, data, *, loader_file_format, refresh=None):
        self.run_call = {"data": data, "loader_file_format": loader_file_format}
        if refresh:
            self.run_call["refresh"] = refresh
        return "loaded"


class FakeDlt:
    def __init__(self) -> None:
        self.config = {}
        self.pipeline_call = None
        self.pipeline_instance = FakePipeline()

    def pipeline(self, *, pipeline_name, destination, dataset_name):
        self.pipeline_call = {
            "pipeline_name": pipeline_name,
            "destination": destination,
            "dataset_name": dataset_name,
        }
        return self.pipeline_instance
