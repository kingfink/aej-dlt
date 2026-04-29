"""Warehouse row builders for repo-backed source content."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from aej_dlt.frontmatter import parse_markdown_document

DEFAULT_DOCS_DIR = "docs"


@dataclass(frozen=True)
class FileTimestamps:
    """Git-derived creation and modification timestamps for one file."""

    created_at: str
    modified_at: str


class GitTimestampResolver:
    """Resolve file timestamps from git history."""

    def __init__(
        self,
        repo_root: Path,
        run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.run_command = run_command

    def __call__(self, file_path: str | Path) -> FileTimestamps:
        relative_path = Path(file_path)
        if relative_path.is_absolute():
            relative_path = relative_path.relative_to(self.repo_root)

        result = self.run_command(
            [
                "git",
                "log",
                "--follow",
                "--format=%aI",
                "--",
                relative_path.as_posix(),
            ],
            cwd=self.repo_root,
            check=True,
            text=True,
            capture_output=True,
        )
        timestamps = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not timestamps:
            raise ValueError(f"No git history found for {relative_path.as_posix()}")

        return FileTimestamps(created_at=timestamps[-1], modified_at=timestamps[0])


def build_job_rows(
    repo_root: Path = Path("."),
    timestamp_resolver: Callable[[Path], FileTimestamps] | None = None,
) -> list[dict[str, Any]]:
    """Build warehouse rows for every job markdown file."""
    repo_root = Path(repo_root)
    jobs_dir = repo_root / DEFAULT_DOCS_DIR / "jobs"
    return _build_rows(repo_root, jobs_dir.rglob("*.md"), timestamp_resolver)


def build_organization_rows(
    repo_root: Path = Path("."),
    timestamp_resolver: Callable[[Path], FileTimestamps] | None = None,
) -> list[dict[str, Any]]:
    """Build warehouse rows for every organization markdown file."""
    repo_root = Path(repo_root)
    orgs_dir = repo_root / DEFAULT_DOCS_DIR / "organizations"
    return _build_rows(repo_root, orgs_dir.glob("*.md"), timestamp_resolver)


def _build_rows(
    repo_root: Path,
    markdown_files,
    timestamp_resolver: Callable[[Path], FileTimestamps] | None,
) -> list[dict[str, Any]]:
    resolver = timestamp_resolver or GitTimestampResolver(repo_root)
    rows = []
    for file_path in sorted(markdown_files):
        if file_path.stem == "index":
            continue

        relative_path = file_path.relative_to(repo_root)
        rows.append(
            build_markdown_row(relative_path, file_path.read_text(encoding="utf-8"), resolver)
        )
    return rows


def build_file_item_rows(
    file_items,
    timestamp_resolver: Callable[[Path], FileTimestamps],
) -> list[dict[str, Any]]:
    """Build warehouse rows from dlt filesystem FileItems."""
    rows = []
    for file_item in file_items:
        relative_path = Path(str(file_item["relative_path"]))
        if relative_path.stem == "index":
            continue
        rows.append(
            build_markdown_row(
                relative_path,
                _read_file_item(file_item),
                timestamp_resolver,
            )
        )
    return rows


def build_markdown_row(
    relative_path: Path,
    markdown_content: str,
    timestamp_resolver: Callable[[Path], FileTimestamps],
) -> dict[str, Any]:
    """Build one warehouse row from markdown content and git timestamps."""
    document = parse_markdown_document(markdown_content)
    timestamps = timestamp_resolver(relative_path)
    return {
        "file_path": relative_path.as_posix(),
        "frontmatter": _json_safe(document.frontmatter),
        "content": document.content,
        "created_at": timestamps.created_at,
        "modified_at": timestamps.modified_at,
        "modified_at_cursor": _modified_at_cursor(timestamps.modified_at, relative_path),
    }


def _read_file_item(file_item) -> str:
    with file_item.open() as file:
        content = file.read()
    if isinstance(content, bytes):
        return content.decode("utf-8")
    return str(content)


def _json_safe(value):
    """Convert PyYAML scalar types into values suitable for a JSON column."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _modified_at_cursor(modified_at: str, relative_path: Path) -> str:
    timestamp = modified_at.replace("Z", "+00:00")
    modified_datetime = datetime.fromisoformat(timestamp)
    if modified_datetime.tzinfo is None:
        modified_datetime = modified_datetime.replace(tzinfo=UTC)
    normalized_timestamp = modified_datetime.astimezone(UTC).isoformat(timespec="microseconds")
    return f"{normalized_timestamp}|{relative_path.as_posix()}"
