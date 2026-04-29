"""Markdown frontmatter parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class MarkdownDocument:
    """Parsed markdown document with YAML frontmatter and body content."""

    frontmatter: dict
    content: str


def read_markdown_document(path: Path) -> MarkdownDocument:
    """Return parsed frontmatter and body content for a markdown file."""
    return parse_markdown_document(path.read_text(encoding="utf-8"))


def parse_markdown_document(content: str) -> MarkdownDocument:
    """Parse frontmatter and body content from a markdown string."""
    metadata, body = _split_frontmatter(content)
    return MarkdownDocument(frontmatter=metadata or {}, content=body)


def _split_frontmatter(content: str) -> tuple[dict | None, str]:
    """Split markdown into parsed frontmatter and body."""
    if not content.startswith("---"):
        return None, content

    end = content.find("---", 3)
    if end == -1:
        return None, content

    raw_block = content[3:end].strip("\n")
    body = content[end + 3 :]

    try:
        metadata = yaml.safe_load(raw_block)
    except yaml.YAMLError:
        return None, body

    if not isinstance(metadata, dict):
        return None, body

    return metadata, body
