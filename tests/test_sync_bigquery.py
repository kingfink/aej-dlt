"""Tests for the AEJ BigQuery sync wrapper."""

from __future__ import annotations

import os
from pathlib import Path

from tailor_made_dlt_sources.git_repo_markdown_files import FileTimestamps

from aej_dlt.sync_bigquery import AEJ_RESOURCE_GLOBS, build_dlt_resources, sync_rows


def test_build_dlt_resources_uses_aej_resource_globs() -> None:
    dlt = FakeDlt()
    filesystem = FakeFilesystem(
        {
            "docs/jobs/**/*.md": [
                FakeFileItem("docs/jobs/acme/job.md", "---\ntitle: Job\n---\nJob\n"),
                FakeFileItem("docs/jobs/index.md", "---\ntitle: Index\n---\n"),
            ],
            "docs/organizations/*.md": [
                FakeFileItem("docs/organizations/acme.md", "---\ntitle: Acme\n---\nOrg\n")
            ],
        }
    )

    resources = build_dlt_resources(
        dlt,
        repo_root=Path("/repo"),
        filesystem_resource=filesystem,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at=f"created:{path.as_posix()}",
            modified_at="2026-01-01T00:00:00+00:00",
        ),
    )

    assert AEJ_RESOURCE_GLOBS == {
        "jobs": "docs/jobs/**/*.md",
        "organizations": "docs/organizations/*.md",
    }
    assert filesystem.calls == [
        {"bucket_url": Path("/repo").as_uri(), "file_glob": "docs/jobs/**/*.md"},
        {"bucket_url": Path("/repo").as_uri(), "file_glob": "docs/organizations/*.md"},
    ]
    assert [call["name"] for call in dlt.resource_calls] == ["jobs", "organizations"]
    assert [resource.name for resource in resources] == ["jobs", "organizations"]
    assert list(resources[0]()) == [
        {
            "file_path": "docs/jobs/acme/job.md",
            "frontmatter": {"title": "Job"},
            "content": "\nJob\n",
            "created_at": "created:docs/jobs/acme/job.md",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "modified_at_cursor": "2026-01-01T00:00:00.000000+00:00|docs/jobs/acme/job.md",
        }
    ]


def test_sync_rows_configures_bigquery_pipeline_and_jsonl(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("BIGQUERY_DATASET", "aej")
    monkeypatch.setenv("BIGQUERY_LOCATION", "US")
    dlt = FakeDlt()
    filesystem = FakeFilesystem(
        {
            "docs/jobs/**/*.md": [
                FakeFileItem("docs/jobs/acme/role.md", "---\ntitle: Role\n---\n")
            ],
            "docs/organizations/*.md": [
                FakeFileItem("docs/organizations/acme.md", "---\ntitle: Acme\n---\n")
            ],
        }
    )

    load_info = sync_rows(
        repo_root=Path("/repo"),
        dlt_module=dlt,
        filesystem_resource=filesystem,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2026-01-01T00:00:00+00:00",
        ),
    )

    assert load_info == "loaded"
    assert dlt.config == {
        "destination.bigquery.project_id": "warehouse-project",
        "destination.bigquery.location": "US",
    }
    assert dlt.pipeline_call == {
        "pipeline_name": "aej_repo_content",
        "destination": "bigquery",
        "dataset_name": "aej",
    }
    assert dlt.pipeline_instance.run_call["loader_file_format"] == "jsonl"
    assert len(dlt.pipeline_instance.run_call["data"]) == 2


def test_sync_rows_can_request_drop_data_refresh(monkeypatch) -> None:
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("BIGQUERY_DATASET", "aej")
    dlt = FakeDlt()
    filesystem = FakeFilesystem(
        {
            "docs/jobs/**/*.md": [
                FakeFileItem("docs/jobs/acme/role.md", "---\ntitle: Role\n---\n")
            ],
            "docs/organizations/*.md": [
                FakeFileItem("docs/organizations/acme.md", "---\ntitle: Acme\n---\n")
            ],
        }
    )

    sync_rows(
        repo_root=Path("/repo"),
        dlt_module=dlt,
        filesystem_resource=filesystem,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2026-01-01T00:00:00+00:00",
        ),
        full_refresh=True,
    )

    assert dlt.pipeline_instance.run_call["refresh"] == "drop_data"


def test_sync_rows_normalizes_escaped_bigquery_private_key(monkeypatch) -> None:
    escaped_private_key = (
        r"-----BEGIN PRIVATE KEY-----\n"
        r"abc123\n"
        r"-----END PRIVATE KEY-----\n"
    )
    monkeypatch.setenv("BIGQUERY_PROJECT", "warehouse-project")
    monkeypatch.setenv("BIGQUERY_DATASET", "aej")
    monkeypatch.setenv(
        "DESTINATION__BIGQUERY__CREDENTIALS__PRIVATE_KEY",
        escaped_private_key,
    )
    dlt = FakeDlt()
    filesystem = FakeFilesystem(
        {
            "docs/jobs/**/*.md": [
                FakeFileItem("docs/jobs/acme/role.md", "---\ntitle: Role\n---\n")
            ],
            "docs/organizations/*.md": [
                FakeFileItem("docs/organizations/acme.md", "---\ntitle: Acme\n---\n")
            ],
        }
    )

    sync_rows(
        repo_root=Path("/repo"),
        dlt_module=dlt,
        filesystem_resource=filesystem,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2026-01-01T00:00:00+00:00",
        ),
    )

    assert os.environ["DESTINATION__BIGQUERY__CREDENTIALS__PRIVATE_KEY"] == (
        "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----\n"
    )


class FakeFileItem:
    def __init__(self, relative_path: str, content: str | bytes) -> None:
        self.relative_path = relative_path
        self.content = content

    def __getitem__(self, key: str):
        if key == "relative_path":
            return self.relative_path
        raise KeyError(key)

    def open(self):
        return FakeOpen(self.content)


class FakeOpen:
    def __init__(self, content: str | bytes) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self):
        return self.content


class FakeFilesystem:
    def __init__(self, files_by_glob) -> None:
        self.files_by_glob = files_by_glob
        self.calls = []

    def __call__(self, *, bucket_url, file_glob):
        self.calls.append({"bucket_url": bucket_url, "file_glob": file_glob})
        return self.files_by_glob[file_glob]


class FakeSources:
    def __init__(self) -> None:
        self.incremental_calls = []

    def incremental(self, cursor_path, *, initial_value, row_order):
        self.incremental_calls.append(
            {
                "cursor_path": cursor_path,
                "initial_value": initial_value,
                "row_order": row_order,
            }
        )
        return {"cursor_path": cursor_path}


class FakePipeline:
    def __init__(self) -> None:
        self.run_call = None

    def run(self, data, *, loader_file_format, refresh=None):
        self.run_call = {
            "data": data,
            "loader_file_format": loader_file_format,
        }
        if refresh:
            self.run_call["refresh"] = refresh
        return "loaded"


class FakeDlt:
    def __init__(self) -> None:
        self.config = {}
        self.resource_calls = []
        self.sources = FakeSources()
        self.pipeline_call = None
        self.pipeline_instance = FakePipeline()

    def resource(self, **kwargs):
        self.resource_calls.append(kwargs)

        def decorator(func):
            return FakeResource(kwargs["name"], func)

        return decorator

    def pipeline(self, *, pipeline_name, destination, dataset_name):
        self.pipeline_call = {
            "pipeline_name": pipeline_name,
            "destination": destination,
            "dataset_name": dataset_name,
        }
        return self.pipeline_instance


class FakeResource:
    def __init__(self, name, func) -> None:
        self.name = name
        self.func = func

    def __call__(self):
        return self.func()
