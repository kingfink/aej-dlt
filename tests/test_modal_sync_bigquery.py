"""Tests for the Modal BigQuery sync entrypoint configuration."""

from __future__ import annotations

import ast
from pathlib import Path

MODAL_ENTRYPOINT_PATH = Path("src/aej_dlt/modal_sync_bigquery.py")


def test_modal_entrypoint_uses_aej_dlt_bigquery_secret() -> None:
    tree = ast.parse(MODAL_ENTRYPOINT_PATH.read_text(encoding="utf-8"))

    secret_name = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SECRET_NAME":
                    secret_name = ast.literal_eval(node.value)

    assert secret_name == "aej-dlt-bq-sync"
