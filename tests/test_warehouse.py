"""Tests for loading repo markdown content into warehouse rows."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from aej_dlt.frontmatter import read_markdown_document
from aej_dlt.sync_bigquery import build_dlt_resources, sync_rows
from aej_dlt.warehouse import (
    FileTimestamps,
    GitTimestampResolver,
    build_job_rows,
    build_organization_rows,
)


def test_read_markdown_document_returns_frontmatter_and_body(tmp_path) -> None:
    path = tmp_path / "job.md"
    path.write_text(
        "---\n"
        "title: Analytics Engineer\n"
        "date: 2026-04-22\n"
        "tags:\n"
        "  - SQL\n"
        "---\n"
        "{{ include_template('job.md') }}\n",
        encoding="utf-8",
    )

    document = read_markdown_document(path)

    assert document.frontmatter == {
        "title": "Analytics Engineer",
        "date": date(2026, 4, 22),
        "tags": ["SQL"],
    }
    assert document.content == "\n{{ include_template('job.md') }}\n"


def test_read_markdown_document_uses_empty_frontmatter_when_missing(tmp_path) -> None:
    path = tmp_path / "plain.md"
    path.write_text("# Plain markdown\n", encoding="utf-8")

    document = read_markdown_document(path)

    assert document.frontmatter == {}
    assert document.content == "# Plain markdown\n"


def test_git_timestamp_resolver_uses_oldest_and_newest_history_entries(tmp_path) -> None:
    calls = []

    def fake_run(args, cwd, check, text, capture_output):
        calls.append(
            {
                "args": args,
                "cwd": cwd,
                "check": check,
                "text": text,
                "capture_output": capture_output,
            }
        )
        return SimpleNamespace(stdout="2026-04-22T23:23:35-04:00\n2025-11-01T08:15:00-04:00\n")

    resolver = GitTimestampResolver(tmp_path, run_command=fake_run)

    timestamps = resolver("docs/jobs/acme/analytics-engineer.md")

    assert timestamps == FileTimestamps(
        created_at="2025-11-01T08:15:00-04:00",
        modified_at="2026-04-22T23:23:35-04:00",
    )
    assert calls == [
        {
            "args": [
                "git",
                "log",
                "--follow",
                "--format=%aI",
                "--",
                "docs/jobs/acme/analytics-engineer.md",
            ],
            "cwd": tmp_path,
            "check": True,
            "text": True,
            "capture_output": True,
        }
    ]


def test_git_timestamp_resolver_rejects_files_without_history(tmp_path) -> None:
    def fake_run(args, cwd, check, text, capture_output):
        return SimpleNamespace(stdout="")

    resolver = GitTimestampResolver(tmp_path, run_command=fake_run)

    with pytest.raises(ValueError, match="No git history"):
        resolver("docs/jobs/acme/missing.md")


def test_build_job_rows_are_sorted_and_json_safe(tmp_path) -> None:
    _write_markdown(
        tmp_path / "docs/jobs/acme/z-last.md",
        "---\ntitle: Last\ndate: 2026-04-22\n---\nLast body\n",
    )
    _write_markdown(
        tmp_path / "docs/jobs/acme/a-first.md",
        "---\ntitle: First\ntags:\n  - dbt\n---\nFirst body\n",
    )
    _write_markdown(tmp_path / "docs/jobs/index.md", "---\ntitle: Index\n---\n")

    rows = build_job_rows(
        tmp_path,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at=f"created:{path.as_posix()}",
            modified_at=f"modified:{path.as_posix()}",
        ),
    )

    assert rows == [
        {
            "file_path": "docs/jobs/acme/a-first.md",
            "frontmatter": {"title": "First", "tags": ["dbt"]},
            "content": "\nFirst body\n",
            "created_at": "created:docs/jobs/acme/a-first.md",
            "modified_at": "modified:docs/jobs/acme/a-first.md",
        },
        {
            "file_path": "docs/jobs/acme/z-last.md",
            "frontmatter": {"title": "Last", "date": "2026-04-22"},
            "content": "\nLast body\n",
            "created_at": "created:docs/jobs/acme/z-last.md",
            "modified_at": "modified:docs/jobs/acme/z-last.md",
        },
    ]


def test_build_organization_rows_skip_index_and_use_same_shape(tmp_path) -> None:
    _write_markdown(
        tmp_path / "docs/organizations/acme.md",
        "---\ntitle: Acme\nactive: true\n---\nOrg body\n",
    )
    _write_markdown(tmp_path / "docs/organizations/index.md", "---\ntitle: Index\n---\n")

    rows = build_organization_rows(
        tmp_path,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2026-01-01T00:00:00+00:00",
        ),
    )

    assert rows == [
        {
            "file_path": "docs/organizations/acme.md",
            "frontmatter": {"title": "Acme", "active": True},
            "content": "\nOrg body\n",
            "created_at": "2025-01-01T00:00:00+00:00",
            "modified_at": "2026-01-01T00:00:00+00:00",
        }
    ]


def test_build_dlt_resources_configures_incremental_merge() -> None:
    dlt = FakeDlt()
    filesystem = FakeFilesystem(
        {
            "docs/jobs/**/*.md": [
                FakeFileItem(
                    "docs/jobs/acme/new.md",
                    "---\ntitle: New\n---\nNew body\n",
                    modification_date="2099-01-01T00:00:00+00:00",
                ),
                FakeFileItem(
                    "docs/jobs/acme/old.md",
                    "---\ntitle: Old\n---\nOld body\n",
                    modification_date="2000-01-01T00:00:00+00:00",
                ),
                FakeFileItem("docs/jobs/index.md", "---\ntitle: Index\n---\n"),
            ],
            "docs/organizations/*.md": [
                FakeFileItem("docs/organizations/acme.md", "---\ntitle: Acme\n---\nOrg body\n")
            ],
        }
    )
    resources = build_dlt_resources(
        dlt,
        repo_root=Path("/repo"),
        filesystem_resource=filesystem,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at=f"created:{path.as_posix()}",
            modified_at=(
                "2026-01-03" if path.as_posix() == "docs/jobs/acme/new.md" else "2026-01-01"
            ),
        ),
    )

    assert filesystem.calls == [
        {
            "bucket_url": Path("/repo").as_uri(),
            "file_glob": "docs/jobs/**/*.md",
        },
        {
            "bucket_url": Path("/repo").as_uri(),
            "file_glob": "docs/organizations/*.md",
        },
    ]
    assert dlt.resource_calls == [
        {
            "name": "jobs",
            "primary_key": "file_path",
            "write_disposition": "merge",
            "columns": {
                "file_path": {"data_type": "text"},
                "frontmatter": {"data_type": "json"},
                "content": {"data_type": "text"},
                "created_at": {"data_type": "timestamp"},
                "modified_at": {"data_type": "timestamp"},
            },
        },
        {
            "name": "organizations",
            "primary_key": "file_path",
            "write_disposition": "merge",
            "columns": {
                "file_path": {"data_type": "text"},
                "frontmatter": {"data_type": "json"},
                "content": {"data_type": "text"},
                "created_at": {"data_type": "timestamp"},
                "modified_at": {"data_type": "timestamp"},
            },
        },
    ]
    assert dlt.sources.incremental_calls == [
        {
            "cursor_path": "modified_at",
            "initial_value": "1970-01-01T00:00:00+00:00",
            "row_order": "asc",
        },
        {
            "cursor_path": "modified_at",
            "initial_value": "1970-01-01T00:00:00+00:00",
            "row_order": "asc",
        },
    ]
    assert list(resources[0]()) == [
        {
            "file_path": "docs/jobs/acme/old.md",
            "frontmatter": {"title": "Old"},
            "content": "\nOld body\n",
            "created_at": "created:docs/jobs/acme/old.md",
            "modified_at": "2026-01-01",
        },
        {
            "file_path": "docs/jobs/acme/new.md",
            "frontmatter": {"title": "New"},
            "content": "\nNew body\n",
            "created_at": "created:docs/jobs/acme/new.md",
            "modified_at": "2026-01-03",
        },
    ]
    assert list(resources[1]()) == [
        {
            "file_path": "docs/organizations/acme.md",
            "frontmatter": {"title": "Acme"},
            "content": "\nOrg body\n",
            "created_at": "created:docs/organizations/acme.md",
            "modified_at": "2026-01-01",
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


def _write_markdown(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
            return func

        return decorator

    def pipeline(self, *, pipeline_name, destination, dataset_name):
        self.pipeline_call = {
            "pipeline_name": pipeline_name,
            "destination": destination,
            "dataset_name": dataset_name,
        }
        return self.pipeline_instance


class FakeFilesystem:
    def __init__(self, files_by_glob) -> None:
        self.files_by_glob = files_by_glob
        self.calls = []

    def __call__(self, *, bucket_url, file_glob):
        self.calls.append(
            {
                "bucket_url": bucket_url,
                "file_glob": file_glob,
            }
        )
        return self.files_by_glob[file_glob]


class FakeFileItem(dict):
    def __init__(self, relative_path: str, content: str, modification_date=None) -> None:
        super().__init__(
            relative_path=relative_path,
            file_url=f"file:///repo/{relative_path}",
            modification_date=modification_date,
        )
        self.content = content

    @contextmanager
    def open(self):
        yield StringIO(self.content)
