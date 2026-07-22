"""Tests for AEJ's Netlify Forms BigQuery pipeline."""

from __future__ import annotations

from aej_dlt.netlify_forms import sync_netlify_forms


def test_sync_configures_netlify_dataset_and_source(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("BIGQUERY_LOCATION", "US")
    monkeypatch.setenv("NETLIFY_ACCESS_TOKEN", "secret-token")
    monkeypatch.setenv("NETLIFY_SITE_ID", "site-id")
    dlt = FakeDlt()
    source_calls = []

    def source_factory(**kwargs):
        source_calls.append(kwargs)
        return "netlify-source"

    load_info = sync_netlify_forms(
        dlt_module=dlt,
        source_factory=source_factory,
    )

    assert load_info == "loaded"
    assert dlt.config == {
        "destination.bigquery.project_id": "warehouse-project",
        "destination.bigquery.location": "US",
    }
    assert dlt.pipeline_call == {
        "pipeline_name": "aej_netlify_forms",
        "destination": "bigquery",
        "dataset_name": "netlify",
    }
    assert source_calls == [
        {
            "access_token": "secret-token",
            "site_id": "site-id",
        }
    ]
    assert dlt.pipeline_instance.run_call == {
        "data": "netlify-source",
        "loader_file_format": "jsonl",
    }


def test_sync_can_request_drop_data_refresh(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("NETLIFY_ACCESS_TOKEN", "secret-token")
    monkeypatch.setenv("NETLIFY_SITE_ID", "site-id")
    dlt = FakeDlt()

    sync_netlify_forms(
        dlt_module=dlt,
        source_factory=lambda **kwargs: "netlify-source",
        full_refresh=True,
    )

    assert dlt.pipeline_instance.run_call["refresh"] == "drop_data"


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
