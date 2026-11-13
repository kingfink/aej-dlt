"""Tests for AEJ's Resend broadcasts BigQuery pipeline."""

from __future__ import annotations

from aej_dlt.resend_broadcasts import sync_resend_broadcasts


def test_sync_configures_resend_dataset_and_source(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("BIGQUERY_LOCATION", "US")
    monkeypatch.setenv("RESEND_API_KEY", "secret-token")
    dlt = FakeDlt()
    source_calls = []

    def source_factory(**kwargs):
        source_calls.append(kwargs)
        return "resend-source"

    load_info = sync_resend_broadcasts(
        dlt_module=dlt,
        source_factory=source_factory,
    )

    assert load_info == "loaded"
    assert dlt.config == {
        "destination.bigquery.project_id": "warehouse-project",
        "destination.bigquery.location": "US",
    }
    assert dlt.pipeline_call == {
        "pipeline_name": "aej_resend_broadcasts",
        "destination": "bigquery",
        "dataset_name": "resend",
    }
    assert source_calls == [{"api_key": "secret-token"}]
    assert dlt.pipeline_instance.run_call == {
        "data": "resend-source",
        "loader_file_format": "jsonl",
    }


def test_sync_can_request_drop_data_refresh(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("RESEND_API_KEY", "secret-token")
    dlt = FakeDlt()

    sync_resend_broadcasts(
        dlt_module=dlt,
        source_factory=lambda **kwargs: "resend-source",
        full_refresh=True,
    )

    assert dlt.pipeline_instance.run_call["refresh"] == "drop_data"


def test_sync_uses_dataset_override(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("RESEND_API_KEY", "secret-token")
    monkeypatch.setenv("RESEND_BIGQUERY_DATASET", "resend_dev")
    dlt = FakeDlt()

    sync_resend_broadcasts(
        dlt_module=dlt,
        source_factory=lambda **kwargs: "resend-source",
    )

    assert dlt.pipeline_call["dataset_name"] == "resend_dev"


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
