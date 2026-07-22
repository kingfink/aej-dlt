from __future__ import annotations

from pathlib import Path


def test_repository_uses_flat_package_layout() -> None:
    assert Path("aej_dlt/__init__.py").is_file()
    assert Path("aej_dlt/netlify_forms.py").is_file()
    assert Path("aej_dlt/sync_bigquery.py").is_file()
    assert Path("modal_app.py").is_file()

    assert not Path("src").exists()
    assert not Path("docs").exists()


def test_docs_directory_stays_ignored() -> None:
    assert "docs/" in Path(".gitignore").read_text(encoding="utf-8").splitlines()
