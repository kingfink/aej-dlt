"""Tests for the Netlify Forms source and BigQuery pipeline."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pytest

from aej_dlt.netlify_forms import (
    FORM_SUBMISSION_COLUMNS,
    build_netlify_resource,
    build_submission_rows,
    fetch_netlify_form_submissions,
    sync_netlify_forms,
)


class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_fetches_every_netlify_page() -> None:
    first_page = [{"id": str(index)} for index in range(100)]
    second_page = [{"id": "100"}]
    responses = iter(
        [
            FakeHTTPResponse(json.dumps(first_page).encode()),
            FakeHTTPResponse(json.dumps(second_page).encode()),
        ]
    )
    requests = []

    def opener(request, *, timeout):
        requests.append({"request": request, "timeout": timeout})
        return next(responses)

    submissions = fetch_netlify_form_submissions(
        access_token="secret-token",
        site_id="site-id",
        opener=opener,
    )

    assert len(submissions) == 101
    assert len(requests) == 2
    assert requests[0]["request"].get_header("Authorization") == "Bearer secret-token"
    assert "page=1" in requests[0]["request"].full_url
    assert "page=2" in requests[1]["request"].full_url
    assert requests[0]["timeout"] == 30


def test_builds_stable_raw_rows() -> None:
    rows = build_submission_rows(
        [
            {
                "id": "submission-id",
                "form_id": "form-id",
                "form_name": "job-apply-capture",
                "created_at": "2026-07-21T14:53:49.751Z",
                "data": {
                    "posthog_session_id": "session-id",
                    "email": "person@example.com",
                },
            }
        ],
        loaded_ts=datetime(2026, 7, 22, 16, 30, tzinfo=UTC),
    )

    assert rows == [
        {
            "submission_id": "submission-id",
            "form_id": "form-id",
            "form_name": "job-apply-capture",
            "submitted_ts": "2026-07-21T14:53:49.751Z",
            "form_data": ('{"email":"person@example.com","posthog_session_id":"session-id"}'),
            "loaded_ts": "2026-07-22T16:30:00+00:00",
        }
    ]


def test_rejects_submission_without_id() -> None:
    with pytest.raises(ValueError, match="missing id"):
        build_submission_rows(
            [{"form_name": "newsletter"}],
            loaded_ts=datetime(2026, 7, 22, tzinfo=UTC),
        )


def test_builds_merge_resource() -> None:
    dlt = FakeDlt()

    resource = build_netlify_resource(
        dlt,
        access_token="secret-token",
        site_id="site-id",
        fetcher=lambda **kwargs: [{"id": "submission-id", "data": {}}],
        loaded_ts=datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert dlt.resource_calls == [
        {
            "name": "form_submissions",
            "primary_key": "submission_id",
            "write_disposition": "merge",
            "columns": FORM_SUBMISSION_COLUMNS,
        }
    ]
    assert list(resource) == [
        {
            "submission_id": "submission-id",
            "form_id": None,
            "form_name": None,
            "submitted_ts": None,
            "form_data": "{}",
            "loaded_ts": "2026-07-22T00:00:00+00:00",
        }
    ]


def test_sync_configures_netlify_dataset_and_merge_resource(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("BIGQUERY_LOCATION", "US")
    monkeypatch.setenv("NETLIFY_ACCESS_TOKEN", "secret-token")
    monkeypatch.setenv("NETLIFY_SITE_ID", "site-id")
    dlt = FakeDlt()

    load_info = sync_netlify_forms(
        dlt_module=dlt,
        fetcher=lambda **kwargs: [{"id": "submission-id", "data": {}}],
        loaded_ts=datetime(2026, 7, 22, tzinfo=UTC),
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
    assert dlt.pipeline_instance.run_call["loader_file_format"] == "jsonl"
    assert list(dlt.pipeline_instance.run_call["data"])[0]["submission_id"] == "submission-id"


def test_sync_can_request_drop_data_refresh(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("NETLIFY_ACCESS_TOKEN", "secret-token")
    monkeypatch.setenv("NETLIFY_SITE_ID", "site-id")
    dlt = FakeDlt()

    sync_netlify_forms(
        dlt_module=dlt,
        fetcher=lambda **kwargs: [],
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
        self.resource_calls = []
        self.pipeline_call = None
        self.pipeline_instance = FakePipeline()

    def resource(self, **kwargs):
        self.resource_calls.append(kwargs)

        def decorator(func):
            return func

        return decorator

    def pipeline(self, *, pipeline_name, destination, dataset_name):
        self.pipeline_call = {
            "pipeline_name": pipeline_name,
            "destination": destination,
            "dataset_name": dataset_name,
        }
        return self.pipeline_instance
